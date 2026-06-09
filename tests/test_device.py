import unittest
from pathlib import Path


class DeviceParsingTest(unittest.TestCase):
    def test_parse_device_extracts_fidelities_coordinates_and_errors(self):
        from gate_cutting.device import parse_device

        data = {
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

        device = parse_device(data)

        self.assertIs(device.raw, data)
        self.assertEqual(device.one_q_fidelities, {0: 0.99, 1: 0.98})
        self.assertEqual(device.qubit_coords, {0: (1.0, 2.0), 1: (3.0, 4.0)})
        self.assertEqual(device.cx_fidelities, {(0, 1): 0.75, (1, 0): 0.5})
        self.assertAlmostEqual(device.error_params.one_qubit[0], 0.01)
        self.assertAlmostEqual(device.error_params.one_qubit[1], 0.02)
        self.assertAlmostEqual(device.error_params.two_qubit[(0, 1)], 0.25)
        self.assertAlmostEqual(device.error_params.two_qubit[(1, 0)], 0.5)
        self.assertAlmostEqual(device.error_params.readout[0], 0.12)
        self.assertAlmostEqual(device.error_params.readout[1], 0.0)

    def test_load_device_reads_exp2_device_json(self):
        from gate_cutting.device import load_device

        device = load_device(Path("experiments/exp2/device.json"))

        self.assertEqual(device.name, "A")
        self.assertEqual(device.device_id, "A")
        self.assertEqual(device.qubit_count, 16)
        self.assertEqual(device.coupling_count, 24)
        self.assertEqual(device.qubit_coords[15], (3.0, 3.0))
        self.assertAlmostEqual(device.one_q_fidelities[10], 0.9995)
        self.assertAlmostEqual(device.cx_fidelities[(15, 14)], 0.5234)
        self.assertAlmostEqual(device.error_params.two_qubit[(15, 14)], 0.4766)
        self.assertAlmostEqual(device.error_params.readout[13], 0.7066)

    def test_parse_device_defaults_missing_values(self):
        from gate_cutting.device import parse_device

        device = parse_device({"qubits": [{"id": 7}], "couplings": [{"control": 7, "target": 8}]})

        self.assertEqual(device.one_q_fidelities[7], 1.0)
        self.assertEqual(device.qubit_coords[7], (7.0, 0.0))
        self.assertEqual(device.error_params.one_qubit[7], 0.0)
        self.assertEqual(device.error_params.readout[7], 0.0)
        self.assertEqual(device.cx_fidelities[(7, 8)], 1.0)
        self.assertEqual(device.error_params.two_qubit[(7, 8)], 0.0)


if __name__ == "__main__":
    unittest.main()
