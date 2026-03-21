"""
Locust 性能测试脚本

使用方法:
    # 启动Locust Web界面
    cd /var/smsc/backend/tests/performance
    locust -f locustfile.py --host=http://localhost:8000
    
    # 命令行模式运行
    locust -f locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 -t 60s

参数说明:
    -u: 用户数量
    -r: 每秒新增用户数
    -t: 测试持续时间
"""
import random
import string
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner


# 测试配置
TEST_API_KEY = "test_api_key_12345"
TEST_PHONE_NUMBERS = [
    "+8613800138000",
    "+8613800138001",
    "+8613800138002",
    "+8613800138003",
    "+8613800138004",
]


def generate_random_message(length: int = 50) -> str:
    """生成随机消息内容"""
    return ''.join(random.choices(string.ascii_letters + string.digits + ' ', k=length))


class SMSGatewayUser(HttpUser):
    """
    模拟SMS网关用户行为
    """
    # 请求间隔时间（秒）
    wait_time = between(0.1, 0.5)
    
    def on_start(self):
        """用户启动时执行"""
        self.api_key = TEST_API_KEY
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
    @task(10)
    def send_single_sms(self):
        """
        发送单条短信 - 高频操作
        权重: 10 (最常用的操作)
        """
        phone = random.choice(TEST_PHONE_NUMBERS)
        message = generate_random_message(random.randint(20, 100))
        
        payload = {
            "phone_number": phone,
            "message": message
        }
        
        with self.client.post(
            "/api/v1/sms/send",
            json=payload,
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    response.success()
                else:
                    response.failure(f"API returned error: {data.get('error')}")
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(3)
    def query_sms_status(self):
        """
        查询短信状态 - 中频操作
        权重: 3
        """
        # 使用随机消息ID（实际测试中应该用真实ID）
        message_id = f"msg_test_{random.randint(1, 10000)}"
        
        with self.client.get(
            f"/api/v1/sms/status/{message_id}",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(2)
    def query_balance(self):
        """
        查询余额 - 中频操作
        权重: 2
        """
        with self.client.get(
            "/api/v1/account/balance",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(1)
    def query_account_info(self):
        """
        查询账户信息 - 低频操作
        权重: 1
        """
        with self.client.get(
            "/api/v1/account/info",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


class BatchSMSUser(HttpUser):
    """
    模拟批量发送用户行为
    """
    wait_time = between(1, 3)
    
    def on_start(self):
        """用户启动时执行"""
        self.api_key = TEST_API_KEY
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
    @task
    def send_batch_sms(self):
        """
        发送批量短信
        """
        # 生成批量请求
        batch_size = random.randint(5, 20)
        recipients = []
        
        for _ in range(batch_size):
            recipients.append({
                "phone_number": random.choice(TEST_PHONE_NUMBERS),
                "message": generate_random_message(random.randint(30, 80))
            })
        
        payload = {
            "messages": recipients
        }
        
        with self.client.post(
            "/api/v1/sms/batch",
            json=payload,
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


class AdminUser(HttpUser):
    """
    模拟管理员用户行为
    """
    wait_time = between(2, 5)
    
    def on_start(self):
        """登录获取Token"""
        # 尝试登录
        login_response = self.client.post(
            "/api/v1/admin/login",
            json={
                "username": "admin",
                "password": "admin123"
            }
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            self.token = data.get("access_token", "")
        else:
            self.token = ""
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    @task(5)
    def query_statistics(self):
        """查询统计数据"""
        with self.client.get(
            "/api/v1/admin/reports/daily",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(2)
    def list_channels(self):
        """查询通道列表"""
        with self.client.get(
            "/api/v1/admin/channels",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")
    
    @task(1)
    def list_accounts(self):
        """查询账户列表"""
        with self.client.get(
            "/api/v1/admin/accounts",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


# 事件处理器
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """测试开始时执行"""
    if isinstance(environment.runner, MasterRunner):
        print("===== 性能测试开始 =====")
        print(f"目标主机: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时执行"""
    if isinstance(environment.runner, MasterRunner):
        print("===== 性能测试结束 =====")


# 如果直接运行脚本
if __name__ == "__main__":
    import os
    os.system("locust -f locustfile.py --host=http://localhost:8000")
