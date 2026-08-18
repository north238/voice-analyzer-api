"""ログ設定のテスト

画面とファイルで出す量を変えていること、
そして標準出力に混ざらないことを守る。
"""

import io
import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from utils.logger import logger


def console_handlers():
    return [
        h
        for h in logger.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    ]


def file_handlers():
    return [h for h in logger.handlers if isinstance(h, TimedRotatingFileHandler)]


def test_console_shows_only_problems():
    """画面には警告以上だけを出す

    長い沈黙を挟んで使うツールのため、正常時に画面が動くと
    文字起こし結果の確認を妨げる（R-8）。
    """
    handlers = console_handlers()

    assert len(handlers) == 1
    assert handlers[0].level == logging.WARNING


def test_console_writes_to_stderr():
    """ログは標準エラーへ出す

    標準出力に混ぜると `2>/dev/null` で結果だけを取り出せなくなる。
    """
    assert console_handlers()[0].stream is sys.stderr


def test_file_keeps_details():
    """ファイルには DEBUG まで残す

    マイク入力の異常は再現しにくいため、起きたときに
    情報が残っていないと後から追えない。
    """
    handlers = file_handlers()

    assert len(handlers) == 1
    assert handlers[0].level == logging.DEBUG


def test_logger_passes_debug_to_handlers():
    """ロガー自体が DEBUG を止めていないこと

    ロガーのレベルが WARNING だと、ハンドラの設定に関わらず
    DEBUG がファイルにも届かなくなる。
    """
    assert logger.level <= logging.DEBUG
    assert logger.isEnabledFor(logging.DEBUG)


def test_nothing_goes_to_stdout(monkeypatch, capsys):
    """標準出力には何も出さない。画面へ出るのは警告以上だけ

    ハンドラは設定された時点の標準エラーを保持しているため、
    capsys では拾えない。出力先を差し替えて確かめる。
    """
    written = io.StringIO()
    monkeypatch.setattr(console_handlers()[0], "stream", written)

    logger.debug("デバッグの記録")
    logger.warning("警告の記録")

    assert capsys.readouterr().out == ""
    assert "警告の記録" in written.getvalue()
    assert "デバッグの記録" not in written.getvalue()


def test_does_not_propagate():
    """親ロガーへ伝播させない（同じ行が二重に出るのを防ぐ）"""
    assert logger.propagate is False
