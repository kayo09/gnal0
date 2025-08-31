# Author: I hate it
print("""
___________________________
    _     _   ____     _   
    /    /    /    )   /   
---/----/----/___ /---/----
  /    /    /    |   /     
_(____/____/_____|__/____/_
                           
      """)
import aiohttp
import asyncio
import argparse
import urllib.parse
from typing import List, Optional
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
import logging
import datetime
import traceback
import aiohttp.resolver

def setup_logging():
    """Set up logging to a file for debugging."""
    logging.basicConfig(
        filename=f"dir_enum_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

def read_file(file_path: str) -> List[str]:
    """Read lines from a file, stripping whitespace."""
    try:
        with open(file_path, 'r') as f:
            return [line.rstrip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: Wordlist file {file_path} not found")
        return []

async def check_url(session: aiohttp.ClientSession, base_url: str, dir_name: str, timeout: float = 60.0, filter_size: Optional[int] = None, verbose: bool = False, retries: int = 3) -> Optional[tuple]:
    """Check if a directory exists at the given URL asynchronously with retries."""
    if not base_url.endswith('/'):
        base_url += '/'
    full_url = urllib.parse.urljoin(base_url, dir_name)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "Accept-Encoding": "gzip, deflate"
    }

    for attempt in range(retries):
        try:
            async with session.get(full_url, headers=headers, allow_redirects=True, timeout=timeout, ssl=False) as response:
                content_length = int(response.headers.get('Content-Length', '0'))
                if verbose:
                    print(f"Checked: {full_url} - Status: {response.status}, Content-Length: {content_length}, Attempt: {attempt + 1}")
                logging.debug(f"URL: {full_url}, Status: {response.status}, Content-Length: {content_length}, Attempt: {attempt + 1}")
                if response.status in (200, 301, 302, 307, 308, 401, 403):
                    if filter_size is not None and content_length == filter_size:
                        return None  # Skip if content length matches filter
                    return (full_url, response.status, content_length)
                return None
        except (aiohttp.ClientConnectionError, aiohttp.ClientSSLError) as e:
            error_msg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logging.debug(f"URL: {full_url}, Connection Error: {error_msg}, Attempt: {attempt + 1}")
            if verbose:
                print(f"Connection Error on {full_url}: {error_msg}")
            if attempt < retries - 1:
                await asyncio.sleep(1)  # Wait before retry
            continue
        except aiohttp.ClientResponseError as e:
            error_msg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logging.debug(f"URL: {full_url}, Response Error: {error_msg}, Attempt: {attempt + 1}")
            if verbose:
                print(f"Response Error on {full_url}: {error_log}")
            return None
        except asyncio.TimeoutError as e:
            error_msg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logging.debug(f"URL: {full_url}, Timeout Error: {error_msg}, Attempt: {attempt + 1}")
            if verbose:
                print(f"Timeout on {full_url}: {error_msg}")
            if attempt < retries - 1:
                await asyncio.sleep(1)  # Wait before retry
            continue
        except Exception as e:
            error_msg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logging.debug(f"URL: {full_url}, Unexpected Error: {error_msg}, Attempt: {attempt + 1}")
            if verbose:
                print(f"Unexpected Error on {full_url}: {error_msg}")
            return None
    return None

async def enumerate_directories(urls: List[str], wordlist: List[str], max_concurrent: int = 100, filter_size: Optional[int] = None, verbose: bool = False) -> List[tuple]:
    """Enumerate directories for given URLs using the provided wordlist with live feedback."""
    console = Console()
    results = []
    total_tasks = len(urls) * len(wordlist)
    completed_tasks = 0

    # Use ThreadPoolResolver to avoid DNS issues
    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(resolver=aiohttp.resolver.ThreadedResolver(), limit=max_concurrent)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Scanning directories...", total=total_tasks)
            found_task = progress.add_task("[green]Directories found", total=None, visible=False)

            for url in urls:
                test_urls = [url]
                if url.startswith("http://"):
                    test_urls.append(url.replace("http://", "https://"))
                elif url.startswith("https://"):
                    test_urls.append(url.replace("https://", "http://"))

                for test_url in test_urls:
                    tasks = [check_url(session, test_url, dir_name,filter_size=filter_size, verbose=verbose) for dir_name in wordlist]
                    for fut in asyncio.as_completed(tasks):
                        result = await fut
                        completed_tasks += 1
                        if result:
                            full_url, status_code, content_length = result
                            status = {
                                200: "Accessible",
                                301: "Redirect",
                                302: "Redirect",
                                307: "Redirect",
                                308: "Redirect",
                                401: "Unauthorized (may exist)",
                                403: "Forbidden (may exist)"
                            }.get(status_code, "Unknown")
                            console.print(f"[green]Found: {full_url} - {status} ({status_code}, CL: {content_length})[/green]")
                            results.append(result)
                            progress.update(found_task, visible=True, advance=1, description=f"[green]Directories found: {len(results)}")
                        if completed_tasks % 10 == 0:
                            progress.advance(task, advance=10)
                    remaining = total_tasks - completed_tasks
                    if remaining < 10 and remaining > 0:
                        progress.advance(task, advance=remaining)
                    # Small delay to avoid rate-limiting
                    await asyncio.sleep(0.1)

    return results

def main():
    parser = argparse.ArgumentParser(description='Fast and Robust URL Directory Enumeration Tool with Live Feedback')
    parser.add_argument('-u', '--urls', required=True, help='File containing URLs to scan')
    parser.add_argument('-w', '--wordlist', required=True, help='File containing directory names')
    parser.add_argument('-c', '--concurrent', type=int, default=100, help='Max concurrent requests')
    parser.add_argument('-fs', '--filter-size', type=int, help='Filter responses with this content length')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output for all requests')

    args = parser.parse_args()

    log_filename = f"dir_enum_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        filename=log_filename,
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    urls = read_file(args.urls)
    wordlist = read_file(args.wordlist)

    if not urls or not wordlist:
        print("Error: Empty URLs or wordlist provided")
        return

    print(f"Starting scan with {len(urls)} URLs and {len(wordlist)} directories")

    results = asyncio.run(enumerate_directories(urls, wordlist, args.concurrent, args.filter_size, args.verbose))

    print(f"\nScan completed. Found {len(results)} potential directories")
    print(f"Debug log saved to {log_filename}")

if __name__ == "__main__":
    main()
# see : dub dub dub kayparmar != .com literally
