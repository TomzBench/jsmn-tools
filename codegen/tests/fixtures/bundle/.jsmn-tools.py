from pathlib import Path

HERE = Path(__file__).parent


def collect(loader):
    return [loader.load_resource(HERE / "b.yaml")]
