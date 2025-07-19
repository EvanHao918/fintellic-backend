import sys
sys.path.append('.')

from app.services.filing_downloader import FilingDownloader
import inspect

# 检查FilingDownloader类
print("FilingDownloader methods:")
for name, method in inspect.getmembers(FilingDownloader, predicate=inspect.ismethod):
    if not name.startswith('_'):
        print(f"  {name}: {inspect.signature(method)}")

# 检查download_filing的具体签名
downloader = FilingDownloader()
if hasattr(downloader, 'download_filing'):
    print(f"\ndownload_filing signature: {inspect.signature(downloader.download_filing)}")

# 查看源代码
import app.services.filing_downloader
print(f"\nSource file: {app.services.filing_downloader.__file__}")
