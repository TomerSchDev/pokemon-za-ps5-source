"""Explicit data locations after the user's NAS relocation request."""
from pathlib import Path
import os
NAS=Path(os.environ.get('POKEMON_NAS_WORK_ROOT',r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1'))
def data_root():return NAS/'PS5-13.60/species-lab/import-all-20261030'
def game_root():return NAS/'Research/pokeza-pc/update-2.0.2-20261025/game'
def extracted_root():return NAS/'GameSources/Extracted-20261030'
