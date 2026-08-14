"""命令行接口"""

import click
from rich.console import Console
from rich.table import Table
from rich.progress import track
from .core import SensitiveWordFilter

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """高性能中文敏感词过滤工具"""
    pass


@main.command()
@click.argument("text")
@click.option(
    "-w", "--wordlist", required=True, type=click.Path(exists=True), help="敏感词文件路径"
)
@click.option("-r", "--replacement", default="*", help="替换字符")
def filter(text, wordlist, replacement):
    """过滤文本中的敏感词"""
    filter_obj = SensitiveWordFilter()

    with console.status("[bold green]加载敏感词库..."):
        filter_obj.load_from_file(wordlist)

    result = filter_obj.filter(text, replacement)
    console.print(f"\n[bold cyan]原文:[/bold cyan] {text}")
    console.print(f"[bold green]过滤后:[/bold green] {result}")


@main.command()
@click.argument("text")
@click.option(
    "-w", "--wordlist", required=True, type=click.Path(exists=True), help="敏感词文件路径"
)
@click.option("--highlight", is_flag=True, help="高亮显示敏感词")
def find(text, wordlist, highlight):
    """查找文本中的敏感词"""
    filter_obj = SensitiveWordFilter()

    with console.status("[bold green]加载敏感词库..."):
        filter_obj.load_from_file(wordlist)

    matches = filter_obj.find_all(text)

    if not matches:
        console.print("[green]✓ 未发现敏感词[/green]")
        return

    console.print(f"\n[bold red]发现 {len(matches)} 个敏感词:[/bold red]\n")

    table = Table(show_header=True)
    table.add_column("敏感词", style="red")
    table.add_column("位置", style="cyan")
    table.add_column("内容", style="yellow")

    for match in matches:
        table.add_row(match.word, f"{match.start}-{match.end}", text[match.start : match.end])

    console.print(table)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "-w", "--wordlist", required=True, type=click.Path(exists=True), help="敏感词文件路径"
)
@click.option("-o", "--output", type=click.Path(), help="输出文件路径")
@click.option("-r", "--replacement", default="*", help="替换字符")
def batch(input_file, wordlist, output, replacement):
    """批量处理文件"""
    filter_obj = SensitiveWordFilter()

    with console.status("[bold green]加载敏感词库..."):
        filter_obj.load_from_file(wordlist)

    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    results = []
    for line in track(lines, description="处理中..."):
        results.append(filter_obj.filter(line.rstrip("\n"), replacement) + "\n")

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.writelines(results)
        console.print(f"[green]✓ 已保存到 {output}[/green]")
    else:
        console.print("".join(results))


@main.command()
@click.option(
    "-w", "--wordlist", required=True, type=click.Path(exists=True), help="敏感词文件路径"
)
@click.option("-t", "--text-file", type=click.Path(exists=True), help="测试文本文件")
def benchmark(wordlist, text_file):
    """性能基准测试"""
    import time

    filter_obj = SensitiveWordFilter()

    # 测试加载时间
    start = time.time()
    filter_obj.load_from_file(wordlist)
    load_time = time.time() - start

    stats = filter_obj.get_stats()

    table = Table(title="性能测试结果")
    table.add_column("指标", style="cyan")
    table.add_column("数值", style="green")

    table.add_row("敏感词数量", str(stats["word_count"]))
    table.add_row("加载时间", f"{load_time:.3f}秒")

    if text_file:
        with open(text_file, "r", encoding="utf-8") as f:
            text = f.read()

        start = time.time()
        matches = filter_obj.find_all(text)
        search_time = time.time() - start

        table.add_row("文本长度", f"{len(text)}字符")
        table.add_row("检测时间", f"{search_time*1000:.2f}毫秒")
        table.add_row("发现敏感词", str(len(matches)))

    console.print(table)


@main.command()
@click.option(
    "-w", "--wordlist", required=True, type=click.Path(exists=True), help="敏感词文件路径"
)
def interactive(wordlist):
    """交互模式"""
    filter_obj = SensitiveWordFilter()

    with console.status("[bold green]加载敏感词库..."):
        filter_obj.load_from_file(wordlist)

    console.print("[bold green]交互模式已启动,输入 'quit' 退出[/bold green]\n")

    while True:
        try:
            text = input("请输入文本: ").strip()
            if text.lower() == "quit":
                break

            if not text:
                continue

            matches = filter_obj.find_all(text)
            if matches:
                console.print(
                    f"[red]发现 {len(matches)} 个敏感词: {[m.word for m in matches]}[/red]"
                )
                filtered = filter_obj.filter(text)
                console.print(f"[green]过滤后: {filtered}[/green]\n")
            else:
                console.print("[green]✓ 未发现敏感词[/green]\n")

        except KeyboardInterrupt:
            break

    console.print("\n[yellow]再见![/yellow]")


if __name__ == "__main__":
    main()
