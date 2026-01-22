import time
from typing import Dict, Optional, List
from contextlib import contextmanager
from dataclasses import dataclass, field
from utils.logger import logger


@dataclass
class TimingData:
    """タイミングデータの構造"""

    step_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None

    def finish(self):
        """計測を終了"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time


@dataclass
class PerformanceStats:
    """パフォーマンス統計データ"""

    step_name: str
    count: int = 0
    total_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0
    avg_time: float = 0.0

    def add_timing(self, duration: float):
        """計測結果を追加"""
        self.count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
        self.avg_time = self.total_time / self.count

    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return {
            "count": self.count,
            "total_time": round(self.total_time, 3),
            "min_time": round(self.min_time, 3),
            "max_time": round(self.max_time, 3),
            "avg_time": round(self.avg_time, 3),
        }


class PerformanceMonitor:
    """パフォーマンス計測クラス"""

    def __init__(self):
        self.current_timings: Dict[str, TimingData] = {}
        self.completed_timings: List[TimingData] = []
        self.stats: Dict[str, PerformanceStats] = {}

    @contextmanager
    def measure(self, step_name: str):
        """
        コンテキストマネージャーとして使用し、処理時間を計測

        使用例:
            monitor = PerformanceMonitor()
            with monitor.measure("transcription"):
                result = transcribe_audio(file)
        """
        timing = TimingData(step_name=step_name, start_time=time.time())
        self.current_timings[step_name] = timing

        try:
            yield timing
        finally:
            timing.finish()
            self.completed_timings.append(timing)

            # 統計情報を更新
            if step_name not in self.stats:
                self.stats[step_name] = PerformanceStats(step_name=step_name)
            self.stats[step_name].add_timing(timing.duration)

            # ログ出力
            logger.info(f"⏱️ [{step_name}] 処理時間: {timing.duration:.3f}秒")

            # 現在の計測から削除
            del self.current_timings[step_name]

    def get_timings(self) -> Dict[str, float]:
        """最新の計測結果を取得（ステップ名: 処理時間の辞書）"""
        return {
            timing.step_name: timing.duration
            for timing in self.completed_timings
            if timing.duration is not None
        }

    def get_last_measurement(self, step_name: str) -> float:
        """指定ステップの最新の計測結果を取得"""
        for timing in reversed(self.completed_timings):
            if timing.step_name == step_name and timing.duration is not None:
                return timing.duration
        return 0.0

    def get_total_time(self) -> float:
        """全ステップの合計時間を取得"""
        return sum(
            timing.duration
            for timing in self.completed_timings
            if timing.duration is not None
        )

    def get_stats(self) -> Dict[str, Dict]:
        """統計情報を取得"""
        return {name: stats.to_dict() for name, stats in self.stats.items()}

    def get_summary(self) -> Dict:
        """サマリー情報を取得（最新の計測結果 + 合計時間）"""
        timings = self.get_timings()
        total_time = self.get_total_time()

        return {
            **{k: round(v, 3) for k, v in timings.items()},
            "total_time": round(total_time, 3),
        }

    def reset(self):
        """計測結果をリセット"""
        self.current_timings.clear()
        self.completed_timings.clear()
        logger.debug("🔄 PerformanceMonitor: 計測結果をリセットしました")

    def print_summary(self):
        """サマリーを標準出力に表示"""
        print("\n" + "=" * 50)
        print("パフォーマンスサマリー")
        print("=" * 50)

        for timing in self.completed_timings:
            if timing.duration is not None:
                print(f"  {timing.step_name:20s}: {timing.duration:6.3f}秒")

        print("-" * 50)
        print(f"  {'合計時間':20s}: {self.get_total_time():6.3f}秒")
        print("=" * 50 + "\n")

    def print_stats(self):
        """統計情報を標準出力に表示"""
        print("\n" + "=" * 70)
        print("パフォーマンス統計")
        print("=" * 70)
        print(
            f"{'ステップ名':20s} {'回数':>6s} {'平均':>8s} {'最小':>8s} {'最大':>8s} {'合計':>8s}"
        )
        print("-" * 70)

        for name, stats in self.stats.items():
            print(
                f"{name:20s} "
                f"{stats.count:6d} "
                f"{stats.avg_time:8.3f} "
                f"{stats.min_time:8.3f} "
                f"{stats.max_time:8.3f} "
                f"{stats.total_time:8.3f}"
            )

        print("=" * 70 + "\n")


# グローバル統計用のシングルトンインスタンス
_global_monitor: Optional[PerformanceMonitor] = None


def get_global_monitor() -> PerformanceMonitor:
    """グローバルパフォーマンスモニターを取得"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor


def reset_global_monitor():
    """グローバルパフォーマンスモニターをリセット"""
    global _global_monitor
    if _global_monitor is not None:
        _global_monitor.reset()
