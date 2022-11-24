from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path

import tomli

@dataclass(frozen=True)
class BotSecrets:
    token: str = field(repr=False)

def load_secrets(secrets_file_path: PathLike, /):
    # TODO should have better error handling
    secrets_file_path = Path(secrets_file_path)
    with secrets_file_path.open('rb') as f:
        secrets_data = tomli.load(f)
    return BotSecrets(**secrets_data)
