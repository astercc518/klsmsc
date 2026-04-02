import pytest
from fastapi import status
import io

@pytest.mark.asyncio
@pytest.mark.integration
async def test_data_upload_delete_reupload(client, test_account):
    """
    测试：上传 -> 删除 -> 再次上传同一个号码
    预期：再次上传后，号码应该重新出现在私有库中（status='active', account_id=user_id）
    """
    headers = {"X-API-Key": test_account.api_key}
    phone_number = "8613812345678"
    
    # 1. 首次上传
    csv_content = f"{phone_number}\n"
    file = ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")
    
    upload_res = client.post(
        "/api/v1/data/my-numbers/upload",
        headers=headers,
        data={
            "country_code": "CN",
            "source": "Manual Upload",
            "purpose": "Social"
        },
        files={"file": file}
    )
    assert upload_res.status_code == status.HTTP_200_OK
    assert upload_res.json()["success"] is True
    
    # 验证上传成功（通过 summary）
    summary_res = client.get("/api/v1/data/my-numbers/summary", headers=headers)
    assert summary_res.status_code == status.HTTP_200_OK
    items = summary_res.json()["items"]
    assert any(item["count"] > 0 for item in items)
    
    # 2. 删除数据
    delete_res = client.delete(
        "/api/v1/data/my-numbers",
        headers=headers,
        params={"country": "CN", "source": "Manual Upload", "purpose": "Social"}
    )
    assert delete_res.status_code == status.HTTP_200_OK
    
    # 验证已删除
    summary_res2 = client.get("/api/v1/data/my-numbers/summary", headers=headers)
    items2 = summary_res2.json()["items"]
    # 应该没有任何 active 的数据项
    assert all(item["count"] == 0 for item in items2) or len(items2) == 0
    
    # 3. 再次上传同一个号码
    file2 = ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")
    upload_res2 = client.post(
        "/api/v1/data/my-numbers/upload",
        headers=headers,
        data={
            "country_code": "CN",
            "source": "Manual Upload",
            "purpose": "Social"
        },
        files={"file": file2}
    )
    assert upload_res2.status_code == status.HTTP_200_OK
    
    # 4. 验证是否重新出现在私有库中
    summary_res3 = client.get("/api/v1/data/my-numbers/summary", headers=headers)
    items3 = summary_res3.json()["items"]
    
    # 如果修复成功，这里应该能看到 1 条数据。
    # 修复前，这里会由于 INSERT IGNORE 导致数据依然是 inactive/无主，从而返回 0。
    found = False
    for item in items3:
        if item["country_code"] == "CN" and item["count"] > 0:
            found = True
            break
    
    assert found, "再次上传后的号码未能在私有库中显示"
