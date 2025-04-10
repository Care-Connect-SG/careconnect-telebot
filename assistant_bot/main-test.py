import azure.cognitiveservices.speech as speechsdk
import os

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY") or "your_actual_key"
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION") or "southeastasia"
TEST_AUDIO_PATH = r"assistant_bot\test.wav"


def test_speech_to_text():
    try:
        if not os.path.exists(TEST_AUDIO_PATH):
            raise FileNotFoundError(f"File not found at {TEST_AUDIO_PATH}")

        speech_config = speechsdk.SpeechConfig(
            subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION
        )
        speech_config.speech_recognition_language = "en-US"

        audio_config = speechsdk.audio.AudioConfig(filename=TEST_AUDIO_PATH)
        recognizer = speechsdk.SpeechRecognizer(speech_config, audio_config)

        print("⏳ Recognizing...")
        result = recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            print("✅ Recognized:", result.text)
        else:
            print("❌ Error:", result.reason)
    except Exception as e:
        print("🚨 Exception occurred:", e)


if __name__ == "__main__":
    test_speech_to_text()
