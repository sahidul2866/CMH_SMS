# Third-party speech models

The optional offline Bengali voice uses Meta AI's
`facebook/mms-tts-ben` checkpoint. It is downloaded during the first Windows
or macOS/Linux `run.sh` setup and stored under `backend/data/models/mms-tts-ben`.

- Model: Massively Multilingual Speech — Bengali Text-to-Speech
- Source: https://huggingface.co/facebook/mms-tts-ben
- License: Creative Commons Attribution-NonCommercial 4.0 International
- Intended deployment: non-commercial use within the hospital

The model is not redistributed inside this source archive. The launchers
download it from its publisher once and preserve it locally for offline inference.
