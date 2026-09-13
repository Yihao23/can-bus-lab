import unittest

from vehicle import busload


class FrameBitsTest(unittest.TestCase):
    def test_standard_8_byte_frame(self):
        self.assertEqual(busload.frame_bits(8, worst_case_stuffing=False), 111)
        self.assertEqual(busload.frame_bits(8), 135)   # the number data sheets quote

    def test_extended_costs_20_more_bits(self):
        self.assertEqual(busload.frame_bits(8, extended=True, worst_case_stuffing=False), 131)

    def test_empty_frame(self):
        self.assertEqual(busload.frame_bits(0, worst_case_stuffing=False), 47)

    def test_dlc_range(self):
        with self.assertRaises(ValueError):
            busload.frame_bits(9)


class BusLoadTest(unittest.TestCase):
    def test_forty_messages_at_10ms_on_500k(self):
        msgs = [busload.CyclicMessage(f"m{i}", 8, 10.0) for i in range(40)]
        load = busload.bus_load(msgs, 500_000)
        self.assertAlmostEqual(load, 40 * 135 * 100 / 500_000)   # 1.08 -> not OK
        self.assertGreater(load, 1.0)

    def test_lab_vehicle_is_light(self):
        msgs = [busload.CyclicMessage("ENGINE_DATA", 8, 20), busload.CyclicMessage("ABS_DATA", 8, 20),
                busload.CyclicMessage("BODY_STATUS", 8, 100)]
        self.assertLess(busload.bus_load(msgs, 500_000), 0.05)


if __name__ == "__main__":
    unittest.main()
