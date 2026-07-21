"""Tests for non-destructive stamp storage. QObject works headless (no QApplication)."""
from io import BytesIO
from pathlib import Path
from PIL import Image

from core.stamp_manager import StampManager
from core.image_processing import DEFAULT_EDIT_PARAMS


def make_stamp_file(tmp_path, size=(10, 10)):
    img = Image.new('RGBA', size, (255, 255, 255, 255))
    for x in range(3, 7):
        for y in range(3, 7):
            img.putpixel((x, y), (0, 0, 0, 255))
    path = tmp_path / "source.png"
    img.save(path, 'PNG')
    return str(path)


def test_import_saves_original_and_processed(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    assert stamp_id is not None
    info = mgr.stamps[stamp_id]
    assert Path(info['file']).exists()
    assert Path(info['original_file']).exists()
    assert 'originals' in info['original_file']
    assert info['edits'] == DEFAULT_EDIT_PARAMS
    assert info['original_width'] == 10


def test_import_with_edits_applies_them(tmp_path):
    mgr = StampManager(str(tmp_path))
    edits = {'rotation': 0, 'crop': [3, 3, 7, 7], 'bg_tolerance': 0}
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test", edits=edits)
    info = mgr.stamps[stamp_id]
    assert info['original_width'] == 4          # processed dims recorded
    assert info['original_height'] == 4
    with Image.open(info['original_file']) as orig:
        assert orig.size == (10, 10)            # original untouched


def test_update_stamp_edits_regenerates_processed(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    updates = []
    mgr.stamp_updated.connect(updates.append)
    assert mgr.update_stamp_edits(stamp_id, {'rotation': 0, 'crop': [3, 3, 7, 7], 'bg_tolerance': 0})
    info = mgr.stamps[stamp_id]
    assert info['original_width'] == 4
    assert info['aspect_ratio'] == 1.0
    assert info['edits']['crop'] == [3, 3, 7, 7]
    assert updates == [stamp_id]


def test_update_stamp_edits_rejects_empty_result(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    assert not mgr.update_stamp_edits(stamp_id, {'rotation': 0, 'crop': [2, 2, 2, 8], 'bg_tolerance': 0})


def test_legacy_stamp_migrates_lazily(tmp_path):
    mgr = StampManager(str(tmp_path))
    stamp_id = mgr.import_stamp(make_stamp_file(tmp_path), "test")
    # Simulate a stamp imported before this feature existed
    original_path = Path(mgr.stamps[stamp_id]['original_file'])
    original_path.unlink()
    del mgr.stamps[stamp_id]['original_file']
    del mgr.stamps[stamp_id]['edits']
    mgr._save_metadata()

    data = mgr.get_original_data(stamp_id)
    assert data is not None
    assert 'original_file' in mgr.stamps[stamp_id]
    assert Path(mgr.stamps[stamp_id]['original_file']).exists()
