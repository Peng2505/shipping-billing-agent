"""Test doubles. Only used by unit tests; never by application code."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from billing_agent.services.oss_storage import StorageError, TempObject


class FakeUrlProvider:
    name = "fake_storage"

    def __init__(self, *, fail_upload=False, fail_delete=False, expires_in=1800,
                 url="https://bucket.example.com/ocr-tmp/x.pdf?Signature=abc"):
        self.fail_upload = fail_upload
        self.fail_delete = fail_delete
        self.expires_in = expires_in
        self.url = url
        self.uploaded: list[tuple[str, int, str]] = []
        self.deleted: list[str] = []

    def put_temporary(self, data: bytes, suffix: str, content_type: str) -> TempObject:
        if self.fail_upload:
            raise StorageError("UPLOAD_FAILED", "OSS upload failed: ConnectionError")
        key = f"ocr-tmp/test/{len(self.uploaded)}{suffix}"
        self.uploaded.append((key, len(data), content_type))
        return TempObject(key=key, url=self.url,
                          expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.expires_in))

    def delete(self, key: str) -> None:
        if self.fail_delete:
            raise StorageError("DELETE_FAILED", "OSS delete failed: ServerError")
        self.deleted.append(key)


class FakeOssBucket:
    def __init__(self, *, fail_put=False, sign_scheme="https"):
        self.fail_put = fail_put
        self.sign_scheme = sign_scheme
        self.objects: dict[str, tuple[bytes, dict]] = {}
        self.sign_calls: list[tuple] = []

    def put_object(self, key, data, headers=None):
        if self.fail_put:
            raise ConnectionError("network down")
        self.objects[key] = (data, headers or {})

    def sign_url(self, method, key, expires, slash_safe=False):
        self.sign_calls.append((method, key, expires, slash_safe))
        return f"{self.sign_scheme}://bucket.oss-cn-test.aliyuncs.com/{key}?Expires={expires}&Signature=s"

    def delete_object(self, key):
        self.objects.pop(key, None)


def ocr_payload(items=None, success=True):
    return {
        "data": {
            "createDate": "2026-10-30 16:53:37",
            "fileName": "",
            "list": items if items is not None else [{
                "fileType": "PAI-COLOADER-NOTICE",
                "invoiceNumber": "SYN-INV-9",
                "chargeList": [{"chargeItem": "Handling Fee", "amount": "40.00", "chargeCtr": ""}],
                "ctrList": [],
                "suspicious": "N",
                "page_index": [0, 1],
            }],
            "orderType": "SYNTHETIC",
            "pages_split": [[0, 1]],
        },
        "success": success,
        "message": "文档处理成功" if success else "处理失败",
        "error_code": None if success else "E1",
        "task_id": None,
    }
