from apps.api.schemas import ImportRecord


def parse_json_records(records: list[dict]) -> list[ImportRecord]:
    return [ImportRecord(**record) for record in records]
