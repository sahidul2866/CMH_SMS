from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any


@dataclass(frozen=True)
class Announcement:
    token_number: str
    patient_name: str
    service_number: str | None
    doctor_name: str
    room_number: str
    language: str = "en"
    repeat_count: int = 1
    rate: int = 150
    voice_mode: str = "auto"
    cache_max_files: int = 40


class AnnouncementEngine:
    """Serialised, backend-hosted speech playback for the connected hospital PA."""

    def __init__(self) -> None:
        self.enabled = os.getenv("CMH_SMS_AUDIO_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self.cache_dir = Path(os.getenv("CMH_SMS_AUDIO_CACHE", "data/announcement-cache"))
        self.playback_command = os.getenv("CMH_SMS_AUDIO_PLAY_COMMAND", "")
        self.prompt_dir = Path(__file__).with_name("audio")
        # One unbounded FIFO is shared by every doctor. The single worker below
        # prevents overlapping announcements and ensures rapid calls are not lost.
        self._queue: asyncio.Queue[Announcement] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self.current_announcement: str | None = None
        self.completed_count = 0
        self.last_error: str | None = None
        self.last_announcement: str | None = None

    async def start(self) -> None:
        if self.enabled and self._worker is None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._worker = asyncio.create_task(self._run(), name="cmh-announcement-worker")

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def enqueue(self, token: Any, settings: dict | None = None) -> bool:
        if not self.enabled:
            return False
        values = settings or {}
        language = values.get("language")
        if not language:
            language_order = values.get("language_order", ["en"])
            if isinstance(language_order, list):
                normalized = [str(item).lower() for item in language_order]
                language = "both" if {"bn", "en"}.issubset(normalized) else (normalized[0] if normalized else "en")
            else:
                language = "en"
        item = Announcement(
            token_number=token.token_number,
            patient_name=token.patient_name,
            service_number=getattr(token, "service_number", None),
            doctor_name=getattr(token, "doctor_name", "your radiographer"),
            room_number=token.room_number,
            language=str(language),
            repeat_count=max(1, min(int(values.get("repeat_count", 1)), 3)),
            rate=max(80, min(int(float(values.get("rate", 0.88)) * 170), 260)),
            voice_mode=str(values.get("voice_mode", "auto")),
            cache_max_files=max(10, min(int(values.get("cache_max_files", 40)), 500)),
        )
        self._queue.put_nowait(item)
        return True

    def status(self) -> dict:
        synthesizer = self._synthesizer()
        player = self._player()
        return {
            "enabled": self.enabled,
            "ready": synthesizer is not None and player is not None if self.enabled else False,
            "synthesizer": Path(synthesizer).name if synthesizer else None,
            "player": Path(player).name if player else None,
            "bangla_supported": self._offline_neural_ready() or self._bangla_prompts_available() or self._bangla_supported(synthesizer),
            "offline_neural_ready": self._offline_neural_ready(),
            "queued": self._queue.qsize(),
            "current_announcement": self.current_announcement,
            "completed_count": self.completed_count,
            "last_announcement": self.last_announcement,
            "last_error": self.last_error,
        }

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            self.current_announcement = item.token_number
            try:
                paths = await asyncio.to_thread(self._prepare, item)
                for _ in range(item.repeat_count):
                    for path in paths:
                        await asyncio.to_thread(self._play, path)
                self.last_announcement = item.token_number
                self.completed_count += 1
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
            finally:
                self.current_announcement = None
                self._queue.task_done()

    def _prepare(self, item: Announcement) -> list[Path]:
        language = item.language.lower()
        paths: list[Path] = []
        allow_neural = getattr(item, "voice_mode", "auto") == "auto"

        def synthesise(text: str, voice: str) -> Path:
            if getattr(item, "voice_mode", "auto") == "offline_neural" and voice == "bn_female":
                try:
                    return self._synthesise_offline_bengali(text, item.rate)
                except Exception:
                    pass
            if allow_neural:
                return self._synthesise(text, voice, item.rate)
            return self._synthesise(text, voice, item.rate, allow_neural=False)

        if language in {"bn", "bangla", "both"}:
            service_number = getattr(item, "service_number", None)
            # Keep the complete sentence in one generated clip. Splicing the
            # dynamic name/token between prerecorded prompts made the speaker,
            # volume and cadence change halfway through the announcement.
            paths.append(
                synthesise(
                    (f"সার্ভিস নম্বর {self._bangla_identifier(service_number)}, " if service_number else "")
                    + f"রোগী {item.patient_name}, অনুগ্রহ করে কক্ষ নম্বর "
                    f"{self._bangla_identifier(item.room_number)}-এ যান।",
                    "bn_female",
                )
            )

        if language in {"en", "english", "both"} or not paths:
            doctor_name = getattr(item, "doctor_name", "your radiographer")
            service_number = getattr(item, "service_number", None)
            identity = f"Service number {service_number}, {item.patient_name}" if service_number else item.patient_name
            paths.append(
                synthesise(
                    f"{identity}, please proceed to "
                    f"{doctor_name}, room {item.room_number}.",
                    "en_male",
                )
            )
        self._prune_cache(getattr(item, "cache_max_files", 40), keep=set(paths))
        return paths

    def _bangla_prompts_available(self) -> bool:
        return all((self.prompt_dir / name).is_file() for name in ("bangla-intro.wav", "bangla-outro.wav"))

    def _synthesise(self, text: str, voice: str, rate: int, *, allow_neural: bool = True) -> Path:
        if allow_neural and voice in {"bn_female", "en_female", "en_male"} and os.getenv("CMH_SMS_NEURAL_TTS", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            try:
                return self._synthesise_neural(text, voice, rate)
            except Exception:
                # Announcements must still work during an internet outage.
                # The existing offline system voice remains the safe fallback.
                pass

        synthesizer = self._synthesizer()
        if not synthesizer:
            raise RuntimeError(
                "No speech synthesizer found; install espeak-ng on Linux or use macOS with the built-in say command"
            )
        is_macos_say = Path(synthesizer).name == "say"
        macos_voice = self._macos_voice(voice) if is_macos_say else None
        engine_voice = {
            "bn_female": "bn",
            "en_female": "en+f3",
            "en_male": "en",
        }.get(voice, voice)
        digest = hashlib.sha256(
            f"v4|{Path(synthesizer).name}|{macos_voice or engine_voice}|{rate}|{text}".encode()
        ).hexdigest()[:24]
        output = self.cache_dir / f"{digest}.{'aiff' if is_macos_say else 'wav'}"
        if not output.exists():
            if is_macos_say:
                command = [synthesizer]
                if macos_voice:
                    command.extend(["-v", macos_voice])
                command.extend(["-r", str(rate), "-o", str(output), text])
            else:
                command = [synthesizer, "-v", engine_voice, "-s", str(rate), "-w", str(output), text]
            subprocess.run(command, check=True, capture_output=True, text=True)
        return output

    def _prune_cache(self, maximum: int, *, keep: set[Path] | None = None) -> None:
        """Retain only the newest bounded set of generated audio files."""
        protected = {path.resolve() for path in (keep or set())}
        files = sorted(
            (path for path in self.cache_dir.glob("*") if path.is_file() and not path.name.startswith(".")),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        retained = 0
        for path in files:
            if path.resolve() in protected or retained < maximum:
                retained += 1
                continue
            path.unlink(missing_ok=True)

    def _synthesise_neural(self, text: str, voice: str, rate: int) -> Path:
        import edge_tts
        import miniaudio

        neural_voice = {
            "bn_female": "bn-BD-NabanitaNeural",
            "en_female": "en-US-JennyNeural",
            "en_male": "en-IN-PrabhatNeural",
        }[voice]
        rate_percent = round((rate / 150 - 1) * 100)
        spoken_rate = f"{rate_percent:+d}%"
        digest = hashlib.sha256(f"neural-v1|{neural_voice}|{spoken_rate}|{text}".encode()).hexdigest()[:24]
        output = self.cache_dir / f"{digest}.wav"
        if output.exists():
            return output

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_dir / f".{digest}.mp3"
        try:
            asyncio.run(edge_tts.Communicate(text, neural_voice, rate=spoken_rate).save(str(temporary)))
            decoded = miniaudio.decode_file(str(temporary), nchannels=1, sample_rate=24000)
            miniaudio.wav_write_file(str(output), decoded)
        finally:
            temporary.unlink(missing_ok=True)
        return output

    def _offline_neural_dir(self) -> Path:
        return Path(os.getenv("CMH_SMS_OFFLINE_TTS_MODEL", "data/models/mms-tts-ben"))

    def _offline_neural_ready(self) -> bool:
        model_dir = self._offline_neural_dir()
        return model_dir.is_dir() and any(model_dir.glob("model*.safetensors"))

    def _synthesise_offline_bengali(self, text: str, rate: int) -> Path:
        """Generate natural Bengali locally with the installed Meta MMS VITS model."""
        import numpy as np
        import torch
        from scipy.io.wavfile import write as write_wav
        from transformers import AutoTokenizer, VitsModel

        model_dir = self._offline_neural_dir()
        if not self._offline_neural_ready():
            raise RuntimeError("Offline Bengali neural model is not installed")
        digest = hashlib.sha256(f"mms-ben-v1|{rate}|{text}".encode()).hexdigest()[:24]
        output = self.cache_dir / f"{digest}.wav"
        if output.exists():
            return output

        tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        model = VitsModel.from_pretrained(model_dir, local_files_only=True)
        inputs = tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            waveform = model(**inputs).waveform[0].cpu().float().numpy()
        peak = max(float(np.max(np.abs(waveform))), 1e-6)
        pcm = np.int16(np.clip(waveform / peak, -1, 1) * 32767)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        write_wav(output, model.config.sampling_rate, pcm)
        return output

    def _play(self, path: Path) -> None:
        if self.playback_command:
            command = Template(self.playback_command).safe_substitute(file=str(path))
            subprocess.run(command, check=True, shell=True)
            return
        if os.name == "nt":
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return
        player = self._player()
        if not player:
            raise RuntimeError("No audio player found; install ALSA utilities on Linux")
        subprocess.run([player, str(path)], check=True, capture_output=True, text=True)

    @staticmethod
    def _synthesizer() -> str | None:
        discovered = shutil.which("espeak-ng") or shutil.which("espeak") or shutil.which("say")
        if discovered:
            return discovered
        if os.name == "nt":
            candidates = [
                Path(os.getenv("ProgramFiles", r"C:\Program Files")) / "eSpeak NG" / "espeak-ng.exe",
                Path(os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "eSpeak NG" / "espeak-ng.exe",
            ]
            return next((str(path) for path in candidates if path.is_file()), None)
        return None

    @staticmethod
    def _player() -> str | None:
        if os.name == "nt":
            return "winsound"
        return shutil.which("aplay") or shutil.which("paplay") or shutil.which("afplay")

    @staticmethod
    def _bangla_supported(synthesizer: str | None) -> bool:
        if not synthesizer:
            return False
        if Path(synthesizer).name == "say":
            return AnnouncementEngine._macos_voice("bn") is not None
        try:
            result = subprocess.run([synthesizer, "--voices=bn"], check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError):
            return False
        return any(" bn" in f" {line.lower()} " for line in result.stdout.splitlines())

    @staticmethod
    def _macos_voice(language: str) -> str | None:
        normalized = language.lower()
        if normalized not in {"bn", "bangla", "bn_female", "en", "english", "en_female", "en_male"} or not shutil.which("say"):
            return None
        try:
            voices = subprocess.run(["say", "-v", "?"], check=True, capture_output=True, text=True).stdout.splitlines()
        except (OSError, subprocess.CalledProcessError):
            return None
        if normalized in {"bn", "bangla", "bn_female"}:
            preferred_name, preferred_locale = "Piya", "bn_"
        elif normalized == "en_male":
            preferred_name, preferred_locale = "Rishi", "en_in"
        else:
            preferred_name, preferred_locale = "Samantha", "en_us"
        for line in voices:
            columns = line.split()
            if len(columns) >= 2 and columns[0] == preferred_name and columns[1].lower().startswith(preferred_locale):
                return columns[0]
        return None

    @staticmethod
    def _bangla_identifier(value: str) -> str:
        spoken = {
            "0": "শূন্য",
            "1": "এক",
            "2": "দুই",
            "3": "তিন",
            "4": "চার",
            "5": "পাঁচ",
            "6": "ছয়",
            "7": "সাত",
            "8": "আট",
            "9": "নয়",
            "A": "এ",
            "B": "বি",
            "C": "সি",
            "D": "ডি",
            "E": "ই",
            "F": "এফ",
            "G": "জি",
            "H": "এইচ",
            "I": "আই",
            "J": "জে",
            "K": "কে",
            "L": "এল",
            "M": "এম",
            "N": "এন",
            "O": "ও",
            "P": "পি",
            "Q": "কিউ",
            "R": "আর",
            "S": "এস",
            "T": "টি",
            "U": "ইউ",
            "V": "ভি",
            "W": "ডাবলিউ",
            "X": "এক্স",
            "Y": "ওয়াই",
            "Z": "জেড",
        }
        return " ".join(spoken[character] for character in value.upper() if character in spoken)


announcement_engine = AnnouncementEngine()
