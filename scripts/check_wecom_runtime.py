from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.core.config import get_settings


def main() -> int:
    settings = get_settings()
    missing_required: list[str] = []
    if not settings.wecom_corp_id.strip():
        missing_required.append("WECOM_CORP_ID")
    if not settings.wecom_agent_id.strip():
        missing_required.append("WECOM_AGENT_ID")
    if not settings.wecom_secret.strip():
        missing_required.append("WECOM_SECRET")
    if missing_required:
        print(f"Missing required WeCom runtime keys: {', '.join(missing_required)}", file=sys.stderr)
        return 1

    missing_recommended: list[str] = []
    if not settings.wecom_token.strip():
        missing_recommended.append("WECOM_TOKEN")
    if not settings.wecom_encoding_aes_key.strip():
        missing_recommended.append("WECOM_ENCODING_AES_KEY")
    if not settings.enable_real_im_adapters:
        missing_recommended.append("ENABLE_REAL_IM_ADAPTERS=true")

    print("WeCom runtime configuration is minimally valid.")
    if missing_recommended:
        print(f"Recommended but missing: {', '.join(missing_recommended)}")
    else:
        print("Recommended callback and runtime keys are also present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
