import json
from pathlib import Path
from time import sleep

from mininet.net import Mininet

from mininetfed.sim.nodes import FedBrokerNode, FedClientNode, FedServerNode


def _format_seconds(seconds) -> str:
    if seconds is None:
        return "N/A"

    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)

    if h > 0:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


class MininetFed(Mininet):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.nodes = []
        self.broker = None
        self.broker_name = ""

    def addHost(self, name, cls=None, **params):
        n = super().addHost(name, cls, **params)

        if cls is not None and isinstance(cls, type) and issubclass(cls, FedBrokerNode):
            if self.broker:
                raise RuntimeError("Only one FedBrokerNode is allowed.")
            self.broker = n
            self.broker_name = name

        elif cls is not None and isinstance(cls, type) and (
            issubclass(cls, FedServerNode) or issubclass(cls, FedClientNode)
        ):
            self.nodes.append(n)

        return n

    def _find_server_progress_file(self) -> Path | None:
        for node in self.nodes:
            if isinstance(node, FedServerNode):
                return Path(node.server_folder) / "progress.json"
        return None

    def _print_progress_if_changed(self, progress_file: Path, last_signature):
        if not progress_file.exists():
            return last_signature

        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                progress = json.load(f)
        except Exception:
            return last_signature

        signature = (
            progress.get("status"),
            progress.get("round"),
            progress.get("rounds_done"),
            progress.get("current_target_metric_value"),
            progress.get("stop_reason"),
        )

        if signature == last_signature:
            return last_signature

        status = progress.get("status")
        round_id = progress.get("round")
        rounds_done = progress.get("rounds_done")
        rounds_left = progress.get("rounds_left")
        num_rounds = progress.get("num_rounds")

        target_metric = progress.get("target_metric")
        current_metric = progress.get("current_target_metric_value")
        best_metric = progress.get("best_target_metric_value")
        stop_value = progress.get("target_metric_stop_value")

        no_improvement = progress.get("no_improvement_counter")
        patience = progress.get("patience")

        last_duration = progress.get("last_round_duration_sec")
        avg_duration = progress.get("avg_round_duration_sec")
        eta = progress.get("estimated_remaining_sec")

        if status == "finished":
            print("\n[MininetFed] Training finished.")
            print(f"[MininetFed] Rounds executed: {rounds_done}/{num_rounds}")
            print(f"[MininetFed] Stop reason: {progress.get('stop_reason_detail')}")
            return signature

        print(
            "\n[MininetFed] Progress "
            f"round={round_id}, "
            f"done={rounds_done}/{num_rounds}, "
            f"left={rounds_left}, "
            f"last_round={_format_seconds(last_duration)}, "
            f"avg_round={_format_seconds(avg_duration)}, "
            f"eta={_format_seconds(eta)}"
        )

        print(
            "[MininetFed] Stop condition "
            f"target_metric={target_metric}, "
            f"current={current_metric}, "
            f"best={best_metric}, "
            f"stop_value={stop_value}, "
            f"no_improvement={no_improvement}, "
            f"patience={patience}"
        )

        return signature

    def runFed(self, show_term=True):
        if not self.broker:
            raise RuntimeError("You must add a FedBrokerNode to the net.")

        self.broker.run(show_term=show_term)
        broker_address = self.broker.IP(intf=f"{self.broker_name}-eth0")

        done_files = []

        for node in self.nodes:
            done = node.run(
                broker_addr=broker_address,
                show_term=show_term,
            )

            if done is not None:
                done_files.append(done)

        progress_file = self._find_server_progress_file()
        last_signature = None

        while not all(done.exists() for done in done_files):
            if progress_file is not None:
                last_signature = self._print_progress_if_changed(
                    progress_file,
                    last_signature,
                )

            sleep(1)

        if progress_file is not None:
            self._print_progress_if_changed(progress_file, last_signature)

        for done in done_files:
            done.unlink(missing_ok=True)