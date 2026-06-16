from apps.api.schemas import ImportRecord


def normalize_local_text(text: str, sender_name: str = "本地用户") -> ImportRecord:
    return ImportRecord(text=text, sender_name=sender_name, channel="local")
