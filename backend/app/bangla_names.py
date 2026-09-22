"""Offline, editable pronunciation suggestions for Bengali announcements.

Roman spellings are ambiguous: these are suggestions, not verified names.
Common spellings use a small lexicon; other Latin words use phonetic rules.
No patient names are sent to an external transliteration service.
"""
from __future__ import annotations

import re
import unicodedata

COMMON_NAMES = {
    "md": "মোহাম্মদ", "mohammad": "মোহাম্মদ", "mohammed": "মোহাম্মদ", "muhammad": "মুহাম্মদ",
    "mohd": "মোহাম্মদ", "mosammat": "মোসাম্মৎ", "mst": "মোসাম্মৎ", "begum": "বেগম",
    "rahim": "রহিম", "rahman": "রহমান", "rahmaan": "রহমান", "rahmat": "রহমত",
    "uddin": "উদ্দিন", "udddin": "উদ্দিন", "hossain": "হোসেন", "hussain": "হোসেন", "hossein": "হোসেন",
    "hasan": "হাসান", "hassan": "হাসান", "islam": "ইসলাম", "islamul": "ইসলামুল",
    "ahmed": "আহমেদ", "ahmad": "আহমদ", "ali": "আলী", "alam": "আলম", "khan": "খান",
    "abdul": "আব্দুল", "abdur": "আব্দুর", "abdullah": "আব্দুল্লাহ", "karim": "করিম",
    "kabir": "কবির", "jamal": "জামাল", "kamal": "কামাল", "jalal": "জালাল", "bilal": "বিলাল",
    "sahidul": "শহিদুল", "shahidul": "শহিদুল", "shahid": "শহিদ", "shahed": "শাহেদ",
    "shah": "শাহ", "shahadat": "শাহাদাত", "shafiq": "শফিক", "rafiq": "রফিক", "rafique": "রফিক",
    "siddique": "সিদ্দিক", "siddiq": "সিদ্দিক", "siddiqui": "সিদ্দিকী", "sarker": "সরকার", "sarkar": "সরকার",
    "chowdhury": "চৌধুরী", "choudhury": "চৌধুরী", "talukder": "তালুকদার", "haque": "হক", "huq": "হক",
    "miah": "মিয়া", "mia": "মিয়া", "molla": "মোল্লা", "mollah": "মোল্লা", "sheikh": "শেখ",
    "syed": "সৈয়দ", "sayed": "সায়েদ", "saeed": "সাঈদ", "sayeed": "সাঈদ", "sabbir": "সাব্বির",
    "sakib": "সাকিব", "shakib": "সাকিব", "rakib": "রাকিব", "rakibul": "রাকিবুল", "arif": "আরিফ",
    "ariful": "আরিফুল", "asif": "আসিফ", "ashraf": "আশরাফ", "ashraful": "আশরাফুল", "akram": "আকরাম",
    "akbar": "আকবর", "anwar": "আনোয়ার", "anowar": "আনোয়ার", "akhtar": "আখতার", "akter": "আক্তার",
    "aktar": "আক্তার", "akhter": "আখতার", "huda": "হুদা", "nur": "নূর", "noor": "নূর", "nurul": "নূরুল",
    "amin": "আমিন", "aminul": "আমিনুল", "habib": "হাবিব", "habibur": "হাবিবুর", "hafiz": "হাফিজ",
    "farhan": "ফারহান", "farhana": "ফারহানা", "fahim": "ফাহিম", "fahima": "ফাহিমা", "faisal": "ফয়সাল",
    "tanvir": "তানভীর", "tanveer": "তানভীর", "tariq": "তারিক", "tareq": "তারেক", "tarek": "তারেক",
    "nasir": "নাসির", "nasrin": "নাসরিন", "nasreen": "নাসরিন", "nusrat": "নুসরাত", "jahan": "জাহান",
    "ayesha": "আয়েশা", "aisha": "আয়েশা", "fatema": "ফাতেমা", "fatima": "ফাতিমা", "khadija": "খাদিজা",
    "sumaiya": "সুমাইয়া", "sumi": "সুমি", "shamima": "শামীমা", "shamim": "শামীম", "shirin": "শিরিন",
    "salma": "সালমা", "asma": "আসমা", "rima": "রিমা", "rina": "রিনা", "lima": "লিমা", "lina": "লিনা",
    "sultana": "সুলতানা", "sultan": "সুলতান", "parvin": "পারভীন", "parveen": "পারভীন", "yasmin": "ইয়াসমিন",
    "yasin": "ইয়াসিন", "yusuf": "ইউসুফ", "ibrahim": "ইব্রাহিম", "ismail": "ইসমাইল", "iqbal": "ইকবাল",
    "joy": "জয়", "roy": "রায়", "ray": "রায়", "das": "দাস", "dutta": "দত্ত", "datta": "দত্ত",
    "saha": "সাহা", "sen": "সেন", "gopal": "গোপাল", "krishna": "কৃষ্ণ", "chandra": "চন্দ্র",
    "debnath": "দেবনাথ", "bhowmik": "ভৌমিক", "biswas": "বিশ্বাস", "pradip": "প্রদীপ", "pradeep": "প্রদীপ",
    "atiq": "আতিক", "atiqur": "আতিকুর", "atik": "আতিক", "atikur": "আতিকুর", "mahmud": "মাহমুদ",
    "mahbub": "মাহবুব", "mahbuba": "মাহবুবা", "masud": "মাসুদ", "masood": "মাসুদ", "monir": "মনির",
    "munir": "মুনির", "mizan": "মিজান", "mizanur": "মিজানুর", "reza": "রেজা", "reja": "রেজা",
}
LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz", (
    "এ", "বি", "সি", "ডি", "ই", "এফ", "জি", "এইচ", "আই", "জে", "কে", "এল", "এম",
    "এন", "ও", "পি", "কিউ", "আর", "এস", "টি", "ইউ", "ভি", "ডাবলিউ", "এক্স", "ওয়াই", "জেড",
)))
CONSONANTS = {
    "chh": "ছ", "kh": "খ", "gh": "ঘ", "ch": "চ", "jh": "ঝ", "th": "থ", "dh": "ধ",
    "ph": "ফ", "bh": "ভ", "sh": "শ", "ng": "ং", "b": "ব", "c": "ক", "d": "দ",
    "f": "ফ", "g": "গ", "h": "হ", "j": "জ", "k": "ক", "l": "ল", "m": "ম", "n": "ন",
    "p": "প", "q": "ক", "r": "র", "s": "স", "t": "ত", "v": "ভ", "w": "ওয়", "x": "ক্স", "y": "য়", "z": "জ",
}
VOWELS = {"aa": ("আ", "া"), "ee": ("ঈ", "ী"), "oo": ("উ", "ু"), "ai": ("ঐ", "ৈ"),
          "oi": ("ঐ", "ৈ"), "ou": ("ঔ", "ৌ"), "a": ("আ", "া"), "i": ("ই", "ি"),
          "u": ("উ", "ু"), "e": ("এ", "ে"), "o": ("ও", "ো")}


def _word(word: str) -> str:
    lower = word.lower()
    if lower in COMMON_NAMES:
        return COMMON_NAMES[lower]
    if len(word) == 1 or not any(vowel in lower for vowel in "aeiou"):
        return " ".join(LETTERS[letter] for letter in lower)
    result, pos, after_consonant = "", 0, False
    while pos < len(lower):
        for roman, (independent, dependent) in VOWELS.items():
            if lower.startswith(roman, pos):
                result += dependent if after_consonant else independent
                pos += len(roman)
                after_consonant = False
                break
        else:
            for roman, bengali in CONSONANTS.items():
                if lower.startswith(roman, pos):
                    if after_consonant:
                        result += "্"
                    result += bengali
                    pos += len(roman)
                    after_consonant = roman not in {"ng", "w"}
                    break
            continue
        continue
    return result


def suggest_bengali_name(name: str) -> str:
    # Decompose Latin accents only; Bengali vowel marks must remain intact.
    normalized = "".join(
        char if '\u0980' <= char <= '\u09ff' else
        "".join(part for part in unicodedata.normalize('NFKD', char) if not unicodedata.combining(part))
        for char in name
    )
    words = re.findall(r"[A-Za-z]+|[\u0980-\u09ff\u200c\u200d]+", normalized)
    result = " ".join(_word(word) if word.isascii() else word for word in words)
    return result if len(result) <= 480 else ""


def validate_bengali_name(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    allowed = all('\u0980' <= char <= '\u09ff' or char.isspace() or char in ".,।-'’()\u200c\u200d" for char in value)
    has_letter = any('\u0980' <= char <= '\u09ff' and unicodedata.category(char).startswith('L') for char in value)
    if not allowed or not has_letter:
        raise ValueError("Use Bengali letters for the announcement name, or leave it blank for an automatic suggestion")
    return value
