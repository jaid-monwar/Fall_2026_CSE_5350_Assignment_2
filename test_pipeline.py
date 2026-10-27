"""Run with: python3 -B -m unittest -v test_pipeline.py."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import assembler
import cat2
import execute


class PipelineTests(unittest.TestCase):
    def run_program(self, source=None, filename=None, pipeline=True):
        with tempfile.TemporaryDirectory() as directory:
            if source is not None:
                filename = Path(directory) / "check.asm"
                filename.write_text("go 0\n" + source + "\nend\n", encoding="utf-8")
            else:
                filename = Path(__file__).parent / filename
            image = Path(directory) / "check.aout"
            assembler.assemble(filename, image)
            with contextlib.redirect_stdout(io.StringIO()):
                result = execute.run_vm(image, pipeline=pipeline, trace=False, max_cycles=1000)
            return result, list(execute.mem)

    def assert_timing(self, result, count, cycles, data=0, control=0):
        self.assertEqual(result["ic"], count)
        self.assertEqual(result["clock"], cycles)
        self.assertEqual(result["pipeline"]["data_stalls"], data)
        self.assertEqual(result["pipeline"]["control_stalls"], control)

    def test_independent_instructions_overlap_and_halt_drains(self):
        result, _ = self.run_program("ldi 1 1\nldi 2 2\nldi 3 3\nsys 1 16")
        self.assert_timing(result, 4, 8)
        self.assertEqual(result["code_refs"], 4)
        self.assertEqual(result["registers"][1:4], [1, 2, 3])

    def test_raw_stalls_for_zero_one_and_two_intervening_instructions(self):
        for gap, stalls in ((0, 2), (1, 1), (2, 0)):
            with self.subTest(gap=gap):
                padding = "ldi 2 0\n" * gap
                result, _ = self.run_program("ldi 1 1\n" + padding + "inc 1\nsys 1 16")
                self.assert_timing(result, 3 + gap, 7 + gap + stalls, data=stalls)
                self.assertEqual(result["registers"][1], 2)
                raw = [event for event in result["pipeline"]["events"] if event["kind"] == "RAW"]
                self.assertEqual([event["stall_cycles"] for event in raw], [stalls] if stalls else [])

    def test_two_pending_writers_wait_for_latest_value(self):
        result, _ = self.run_program("ldi 1 1\nldi 1 2\ninc 1\nsys 1 16")
        self.assert_timing(result, 4, 10, data=2)
        self.assertEqual(result["registers"][1], 3)

    def test_store_and_part1_baseline_remain_reproducible(self):
        result, memory = self.run_program(filename="part1_store.asm")
        self.assert_timing(result, 4, 10, data=2)
        self.assertEqual((memory[4], result["registers"][2]), (42, 42))
        self.assertEqual((result["code_refs"], result["data_refs"], result["total_refs"]), (4, 2, 6))
        baseline, baseline_memory = self.run_program(filename="part1_store.asm", pipeline=False)
        self.assertEqual(baseline["clock"], 20)
        self.assertEqual(result["registers"], baseline["registers"])
        self.assertEqual(memory, baseline_memory)

    def test_indirect_pointer_and_load_use_real_sources(self):
        result, memory = self.run_program(filename="part2_hazards.asm")
        self.assert_timing(result, 8, 20, data=8)
        self.assertEqual([result["registers"][r] for r in (1, 2, 4)], [6, 7, 13])
        self.assertEqual(memory[9], 7)
        self.assertEqual(result["data_refs"], 3)

    def test_indirect_read_waits_for_older_store(self):
        result, memory = self.run_program(
            "ldi 3 .value\nldi 1 42\nst 1 .value\nadd 2 *3\nsys 1 16\n.value dw 0")
        self.assert_timing(result, 5, 12, data=3)
        self.assertEqual(result["registers"][2], 42)
        self.assertEqual(memory[5], 42)
        self.assertEqual(result["data_refs"], 2)

    def test_store_interlock_compares_effective_addresses(self):
        for segment in (0, 200):
            for pointer, stalls, expected in ((101, 0, 7), (100, 1, 42)):
                with self.subTest(segment=segment, pointer=pointer):
                    setup = f"ldi 6 {segment}\n" if segment else ""
                    source = (setup + f"ldi 1 42\nldi 3 {pointer}\nldi 4 0\n"
                              f"st 1 100\nadd 2 *3\nsys 1 16\n"
                              f"{segment + 100} dw 0\n{segment + 101} dw 7")
                    result, memory = self.run_program(source)
                    count = 6 + bool(segment)
                    self.assert_timing(result, count, count + 4 + stalls, data=stalls)
                    self.assertEqual(result["registers"][2], expected)
                    self.assertEqual(memory[segment + 100], 42)
                    # Address comparison must not introduce a memory read.
                    self.assertEqual(result["data_refs"], 2)
                    hazards = [event for event in result["pipeline"]["events"]
                               if event["kind"] == "RAW"]
                    self.assertEqual(len(hazards), stalls)
                    if stalls:
                        self.assertEqual(hazards[0]["memory_address"], segment + 100)
                        self.assertEqual(hazards[0]["stall_cycles"], 1)
                    baseline, baseline_memory = self.run_program(source, pipeline=False)
                    self.assertEqual(result["registers"], baseline["registers"])
                    self.assertEqual(memory, baseline_memory)

    def test_store_address_comparison_waits_for_pointer_register(self):
        result, _ = self.run_program(
            "ldi 3 101\nst 0 100\nadd 2 *3\nsys 1 16\n100 dw 0\n101 dw 7")
        self.assert_timing(result, 4, 9, data=1)
        self.assertEqual(result["registers"][2], 7)
        self.assertEqual(result["data_refs"], 2)
        hazards = [event for event in result["pipeline"]["events"] if event["kind"] == "RAW"]
        self.assertEqual(len(hazards), 1)
        self.assertIn(3, hazards[0]["registers"])
        self.assertIsNone(hazards[0]["memory"])

    def test_data_segment_is_an_implicit_source(self):
        result, _ = self.run_program("ldi 6 100\nld 1 0\nsys 1 16\n100 dw 7")
        self.assert_timing(result, 3, 9, data=2)
        self.assertEqual(result["registers"][1], 7)

    def test_code_segment_writer_blocks_stale_fetches(self):
        result, _ = self.run_program("ldi 7 20\n21 ldi 1 7\nsys 1 16")
        self.assert_timing(result, 3, 10)
        self.assertEqual(result["pipeline"]["serialization_stalls"], 3)
        self.assertEqual(result["registers"][1], 7)
        self.assertEqual(result["code_refs"], 3)

    def test_loop_predictor_updates_and_resets_between_runs(self):
        for _ in range(2):
            result, _ = self.run_program(filename="part2_branches.asm")
            self.assert_timing(result, 8, 24, data=8, control=4)
            self.assertEqual(result["pipeline"]["mispredictions"], 2)
            self.assertEqual(result["pipeline"]["predictor"], {2: False})
            branches = [event for event in result["pipeline"]["events"] if event["kind"] == "BRANCH"]
            self.assertEqual([event["prediction"] for event in branches], ["N", "T", "T"])
            self.assertEqual([event["actual"] for event in branches], ["T", "T", "N"])
            self.assertEqual([event["stall_cycles"] for event in branches], [2, 0, 2])
            self.assertEqual(result["code_refs"], result["ic"] + result["pipeline"]["squashed"])

    def test_correct_not_taken_prediction_has_no_control_penalty(self):
        result, _ = self.run_program(
            "ldi 1 0\nbnz 1 .target\nldi 2 9\nsys 1 16\n.target ldi 2 99\nsys 1 16")
        self.assert_timing(result, 4, 10, data=2)
        self.assertEqual(result["registers"][2], 9)
        self.assertEqual(result["pipeline"]["mispredictions"], 0)

    def test_wrong_path_store_and_illegal_instruction_have_no_side_effects(self):
        for wrong_path in ("st 1 .value", "dw 0"):
            with self.subTest(wrong_path=wrong_path):
                result, memory = self.run_program(
                    "ldi 1 1\nbnz 1 .target\n" + wrong_path +
                    "\nldi 3 99\n.target ldi 2 7\nsys 1 16\n.value dw 0")
                self.assert_timing(result, 4, 12, data=2, control=2)
                self.assertEqual(result["registers"][2:4], [7, 0])
                self.assertEqual(memory[6], 0)
                self.assertEqual(result["data_refs"], 0)
                self.assertIsNone(result["pipeline"]["fault"])

    def test_call_return_and_system_control(self):
        result, _ = self.run_program(filename="part2_control.asm")
        self.assert_timing(result, 5, 13, control=4)
        self.assertEqual((result["registers"][1], result["registers"][5]), (1, 2))
        controls = [event for event in result["pipeline"]["events"] if event["kind"] == "CONTROL"]
        self.assertEqual([event["stall_cycles"] for event in controls], [2, 2])
        self.assertEqual([event["data_stall_cycles"] for event in controls], [0, 0])
        self.assertTrue(all("scoreboard" in event for event in controls))
        self.assertEqual(sum(event["stall_cycles"] for event in controls),
                         result["pipeline"]["control_stalls"])
        result, _ = self.run_program("sys 2 .handler\nsys 1 16\n.handler inc 1\nret 5")
        self.assert_timing(result, 4, 12, control=4)
        self.assertEqual((result["registers"][1], result["registers"][5]), (1, 1))
        controls = [event for event in result["pipeline"]["events"] if event["kind"] == "CONTROL"]
        self.assertEqual([event["stall_cycles"] for event in controls], [2, 2])

    def test_control_report_separates_raw_and_control_stalls(self):
        result, _ = self.run_program("ldi 5 .done\nret 5\nldi 1 99\n.done sys 1 16")
        self.assert_timing(result, 3, 11, data=2, control=2)
        controls = [event for event in result["pipeline"]["events"] if event["kind"] == "CONTROL"]
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["stall_cycles"], 2)
        self.assertEqual(controls[0]["data_stall_cycles"], 2)

    def test_control_report_preserves_code_segment_stall_category(self):
        result, _ = self.run_program("brl 7 1\n2 sys 1 16")
        self.assert_timing(result, 2, 9)
        self.assertEqual(result["pipeline"]["serialization_stalls"], 3)
        controls = [event for event in result["pipeline"]["events"] if event["kind"] == "CONTROL"]
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]["stall_cycles"], 0)
        self.assertTrue(controls[0]["code_segment_wait"])

    def test_scalar_array_sum_matches_baseline(self):
        result, memory = self.run_program(filename="in.asm")
        baseline, baseline_memory = self.run_program(filename="in.asm", pipeline=False)
        self.assertEqual(result["registers"], baseline["registers"])
        self.assertEqual(result["registers"][1], 113)
        self.assertEqual(result["ic"], 24)
        self.assertEqual(result["data_refs"], baseline["data_refs"])
        self.assertEqual(memory, baseline_memory)

    def test_store_to_prefetched_code_replays_before_execution(self):
        replacement = (9 << cat2.OPCPOSITION) | (2 << cat2.REG1POSITION) | 7
        for padding, replay_stalls in (("", 3), ("ldi 3 0\n", 2)):
            with self.subTest(replay_stalls=replay_stalls):
                source = ("ld 1 .replacement\nst 1 .next\n" + padding +
                          ".next ldi 2 99\nsys 1 16\n.replacement dw " + str(replacement))
                result, memory = self.run_program(source)
                baseline, baseline_memory = self.run_program(source, pipeline=False)
                self.assertEqual(result["registers"][2], 7)
                self.assertEqual(result["registers"], baseline["registers"])
                self.assertEqual(memory, baseline_memory)
                self.assertEqual(result["pipeline"]["replay_stalls"], replay_stalls)
                self.assertEqual(result["clock"], 13)


if __name__ == "__main__":
    unittest.main()
