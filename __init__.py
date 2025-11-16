from pathlib import Path

# Ensure utils directory is treated as a package
utils_init = Path(__file__).parent / 'utils' / '__init__.py'
if not utils_init.exists():
    utils_init.parent.mkdir(exist_ok=True)
    utils_init.touch()
