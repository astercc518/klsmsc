"""
基准性能测试脚本

用于测量核心功能的响应时间和吞吐量

使用方法:
    cd /var/smsc/backend
    python -m tests.performance.benchmark
"""
import asyncio
import time
import statistics
from typing import List, Callable
from datetime import datetime


class BenchmarkResult:
    """基准测试结果"""
    
    def __init__(self, name: str, times: List[float]):
        self.name = name
        self.times = times
        self.count = len(times)
        self.total = sum(times)
        self.mean = statistics.mean(times) if times else 0
        self.median = statistics.median(times) if times else 0
        self.min = min(times) if times else 0
        self.max = max(times) if times else 0
        self.stdev = statistics.stdev(times) if len(times) > 1 else 0
        
        # 百分位数
        sorted_times = sorted(times)
        self.p50 = self._percentile(sorted_times, 50)
        self.p95 = self._percentile(sorted_times, 95)
        self.p99 = self._percentile(sorted_times, 99)
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        if not data:
            return 0
        k = (len(data) - 1) * percentile / 100
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        return data[f] + (data[c] - data[f]) * (k - f)
    
    def __str__(self) -> str:
        return f"""
========== {self.name} ==========
执行次数: {self.count}
总耗时: {self.total:.4f}s
平均耗时: {self.mean * 1000:.2f}ms
中位数: {self.median * 1000:.2f}ms
最小值: {self.min * 1000:.2f}ms
最大值: {self.max * 1000:.2f}ms
标准差: {self.stdev * 1000:.2f}ms
P50: {self.p50 * 1000:.2f}ms
P95: {self.p95 * 1000:.2f}ms
P99: {self.p99 * 1000:.2f}ms
TPS: {self.count / self.total:.2f}
================================
"""


async def benchmark_async(
    name: str,
    func: Callable,
    iterations: int = 100,
    warmup: int = 10,
    **kwargs
) -> BenchmarkResult:
    """
    异步函数基准测试
    
    Args:
        name: 测试名称
        func: 异步函数
        iterations: 测试迭代次数
        warmup: 预热次数
        **kwargs: 函数参数
    """
    # 预热
    print(f"正在预热 {name}...")
    for _ in range(warmup):
        await func(**kwargs)
    
    # 正式测试
    print(f"开始测试 {name} ({iterations} 次迭代)...")
    times = []
    
    for i in range(iterations):
        start = time.perf_counter()
        await func(**kwargs)
        end = time.perf_counter()
        times.append(end - start)
        
        if (i + 1) % (iterations // 10) == 0:
            print(f"  进度: {i + 1}/{iterations}")
    
    return BenchmarkResult(name, times)


def benchmark_sync(
    name: str,
    func: Callable,
    iterations: int = 100,
    warmup: int = 10,
    **kwargs
) -> BenchmarkResult:
    """
    同步函数基准测试
    """
    # 预热
    print(f"正在预热 {name}...")
    for _ in range(warmup):
        func(**kwargs)
    
    # 正式测试
    print(f"开始测试 {name} ({iterations} 次迭代)...")
    times = []
    
    for i in range(iterations):
        start = time.perf_counter()
        func(**kwargs)
        end = time.perf_counter()
        times.append(end - start)
        
        if (i + 1) % (iterations // 10) == 0:
            print(f"  进度: {i + 1}/{iterations}")
    
    return BenchmarkResult(name, times)


# ============ 测试用例 ============

async def test_phone_parser():
    """测试电话号码解析性能"""
    from app.core.phone_parser import PhoneNumberParser
    
    phone_numbers = [
        "+8613800138000",
        "+12025551234",
        "+447911123456",
        "+33612345678",
        "+81901234567",
    ]
    
    async def parse_phones():
        for phone in phone_numbers:
            PhoneNumberParser.parse(phone)
    
    result = await benchmark_async(
        "电话号码解析",
        parse_phones,
        iterations=1000,
        warmup=100
    )
    print(result)


async def test_pricing_calculation():
    """测试计费计算性能"""
    from app.core.pricing import PricingEngine
    
    # 创建Mock
    engine = PricingEngine(None)
    
    messages = [
        "Short message",
        "A" * 160,  # 单条边界
        "A" * 200,  # 长短信
        "中文短信测试",
        "中文" * 50,  # 中文长短信
    ]
    
    def calculate_sms_parts():
        for msg in messages:
            engine._count_sms_parts(msg)
    
    result = benchmark_sync(
        "短信计费计算",
        calculate_sms_parts,
        iterations=10000,
        warmup=1000
    )
    print(result)


async def test_gsm7_detection():
    """测试GSM-7编码检测性能"""
    from app.core.pricing import PricingEngine
    
    engine = PricingEngine(None)
    
    messages = [
        "Hello World",
        "Special chars: @£$¥",
        "中文消息",
        "Mixed: Hello 你好",
    ]
    
    def detect_encoding():
        for msg in messages:
            engine._is_gsm7(msg)
    
    result = benchmark_sync(
        "GSM-7编码检测",
        detect_encoding,
        iterations=10000,
        warmup=1000
    )
    print(result)


async def run_all_benchmarks():
    """运行所有基准测试"""
    print("\n" + "=" * 50)
    print("SMS Gateway 基准性能测试")
    print(f"开始时间: {datetime.now().isoformat()}")
    print("=" * 50 + "\n")
    
    # 运行测试
    await test_phone_parser()
    await test_pricing_calculation()
    await test_gsm7_detection()
    
    print("\n" + "=" * 50)
    print("测试完成!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_all_benchmarks())
