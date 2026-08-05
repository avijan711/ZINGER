"""Email sharing attachment handling, with Outlook COM faked."""

from core.share_manager import ShareManager


class FakeMail:
    def __init__(self):
        self.Subject = None
        self.Body = None
        self.displayed = False
        self.Attachments = self
        self.added = []

    def Add(self, path):
        self.added.append(path)

    def Display(self, modal):
        self.displayed = True


class FakeOutlook:
    def __init__(self):
        self.mail = FakeMail()

    def CreateItem(self, item_type):
        return self.mail


def make_manager(monkeypatch):
    manager = ShareManager()
    outlook = FakeOutlook()
    monkeypatch.setattr(manager, "_get_outlook", lambda: outlook)
    return manager, outlook


def test_single_path_string_still_works(monkeypatch, tmp_path):
    manager, outlook = make_manager(monkeypatch)
    f = tmp_path / "signed.pdf"
    f.write_bytes(b"pdf")

    assert manager.share_via_email(str(f)) is True
    assert len(outlook.mail.added) == 1
    assert outlook.mail.added[0].endswith("signed.pdf")
    assert outlook.mail.displayed is True


def test_multiple_attachments(monkeypatch, tmp_path):
    manager, outlook = make_manager(monkeypatch)
    pdf = tmp_path / "signed.pdf"
    pdf.write_bytes(b"pdf")
    docx = tmp_path / "signed.docx"
    docx.write_bytes(b"docx")

    assert manager.share_via_email([str(pdf), str(docx)]) is True
    assert len(outlook.mail.added) == 2


def test_missing_file_returns_false(monkeypatch, tmp_path):
    manager, outlook = make_manager(monkeypatch)
    assert manager.share_via_email(str(tmp_path / "missing.pdf")) is False
    assert outlook.mail.added == []
