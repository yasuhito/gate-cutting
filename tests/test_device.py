import unittest
from pathlib import Path

SAMPLE_DEVICE = {
    "name": "mini",
    "qubits": [
        {
            "id": "0",
            "position": {"x": 1, "y": 2},
            "fidelity": 0.99,
            "meas_error": {"readout_assignment_error": 0.12},
        },
        {
            "id": 1,
            "x": 3,
            "y": 4,
            "fidelity": 0.98,
            "meas_error": {},
        },
    ],
    "couplings": [
        {"control": "0", "target": "1", "fidelity": 0.75, "reverse_fidelity": 0.5},
    ],
}


def parsed_sample_device():
    from gate_cutting.device import parse_device

    return parse_device(SAMPLE_DEVICE)


def loaded_exp2_device():
    from gate_cutting.device import load_device

    return load_device(Path("experiments/exp2/device.json"))


def parsed_default_device():
    from gate_cutting.device import parse_device

    return parse_device({"qubits": [{"id": 7}], "couplings": [{"control": 7, "target": 8}]})


class DeviceParsingTest(unittest.TestCase):
    def test_parse_device_keeps_raw_mapping(self):
        self.assertIs(parsed_sample_device().raw, SAMPLE_DEVICE)

    def test_parse_device_extracts_one_qubit_fidelities(self):
        self.assertEqual(parsed_sample_device().one_q_fidelities, {0: 0.99, 1: 0.98})

    def test_parse_device_extracts_qubit_coordinates(self):
        self.assertEqual(parsed_sample_device().qubit_coords, {0: (1.0, 2.0), 1: (3.0, 4.0)})

    def test_parse_device_extracts_forward_and_reverse_cx_fidelities(self):
        self.assertEqual(parsed_sample_device().cx_fidelities, {(0, 1): 0.75, (1, 0): 0.5})

    def test_parse_device_derives_first_one_qubit_error(self):
        self.assertAlmostEqual(parsed_sample_device().error_params.one_qubit[0], 0.01)

    def test_parse_device_derives_second_one_qubit_error(self):
        self.assertAlmostEqual(parsed_sample_device().error_params.one_qubit[1], 0.02)

    def test_parse_device_derives_forward_two_qubit_error(self):
        self.assertAlmostEqual(parsed_sample_device().error_params.two_qubit[(0, 1)], 0.25)

    def test_parse_device_derives_reverse_two_qubit_error(self):
        self.assertAlmostEqual(parsed_sample_device().error_params.two_qubit[(1, 0)], 0.5)

    def test_parse_device_extracts_readout_error(self):
        self.assertAlmostEqual(parsed_sample_device().error_params.readout[0], 0.12)

    def test_parse_device_defaults_missing_readout_error(self):
        self.assertAlmostEqual(parsed_sample_device().error_params.readout[1], 0.0)

    def test_load_device_reads_exp2_device_name(self):
        self.assertEqual(loaded_exp2_device().name, "A")

    def test_load_device_reads_exp2_device_id(self):
        self.assertEqual(loaded_exp2_device().device_id, "A")

    def test_load_device_counts_exp2_qubits(self):
        self.assertEqual(loaded_exp2_device().qubit_count, 16)

    def test_load_device_counts_exp2_couplings(self):
        self.assertEqual(loaded_exp2_device().coupling_count, 24)

    def test_load_device_reads_exp2_qubit_coordinate(self):
        self.assertEqual(loaded_exp2_device().qubit_coords[15], (3.0, 3.0))

    def test_load_device_reads_exp2_one_qubit_fidelity(self):
        self.assertAlmostEqual(loaded_exp2_device().one_q_fidelities[10], 0.9995)

    def test_load_device_reads_exp2_worst_cx_fidelity(self):
        self.assertAlmostEqual(loaded_exp2_device().cx_fidelities[(15, 14)], 0.5234)

    def test_load_device_derives_exp2_worst_cx_error(self):
        self.assertAlmostEqual(loaded_exp2_device().error_params.two_qubit[(15, 14)], 0.4766)

    def test_load_device_reads_exp2_bad_readout_error(self):
        self.assertAlmostEqual(loaded_exp2_device().error_params.readout[13], 0.7066)

    def test_parse_device_defaults_missing_one_qubit_fidelity(self):
        self.assertEqual(parsed_default_device().one_q_fidelities[7], 1.0)

    def test_parse_device_defaults_missing_qubit_coordinate(self):
        self.assertEqual(parsed_default_device().qubit_coords[7], (7.0, 0.0))

    def test_parse_device_defaults_missing_one_qubit_error(self):
        self.assertEqual(parsed_default_device().error_params.one_qubit[7], 0.0)

    def test_parse_device_defaults_missing_readout_error_to_zero(self):
        self.assertEqual(parsed_default_device().error_params.readout[7], 0.0)

    def test_parse_device_defaults_missing_cx_fidelity(self):
        self.assertEqual(parsed_default_device().cx_fidelities[(7, 8)], 1.0)

    def test_parse_device_defaults_missing_two_qubit_error(self):
        self.assertEqual(parsed_default_device().error_params.two_qubit[(7, 8)], 0.0)


if __name__ == "__main__":
    unittest.main()
