"""
Unit tests for OBD-II Decoder Service
"""
import unittest
from services.obd2_decoder import OBD2Decoder, OBD2Message, OBD2Parameter, OBD2Mode
from services.obd2_poller import OBD2Poller, PIDConfig
import time


class TestOBD2Decoder(unittest.TestCase):
    """Test OBD-II Decoder"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.decoder = OBD2Decoder()
    
    def test_decode_mode_01_request(self):
        """Test decoding Mode 01 request"""
        # Request engine RPM (PID 0x0C)
        data = bytes([0x01, 0x0C])
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        self.assertEqual(message.mode, 0x01)
        self.assertEqual(message.mode_name, "SHOW_CURRENT_DATA")
        self.assertEqual(message.pid, 0x0C)
        self.assertFalse(message.is_response)
    
    def test_decode_engine_rpm(self):
        """Test decoding engine RPM (PID 0x0C)"""
        # Response: RPM = 2500
        # Formula: ((A * 256) + B) / 4
        # 2500 * 4 = 10000 = 0x2710
        data = bytes([0x41, 0x0C, 0x27, 0x10])
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        self.assertTrue(message.is_response)
        self.assertEqual(len(message.parameters), 1)
        
        param = message.parameters[0]
        self.assertEqual(param.name, "engine_rpm")
        self.assertEqual(param.value, 2500.0)
        self.assertEqual(param.unit, "rpm")
    
    def test_decode_vehicle_speed(self):
        """Test decoding vehicle speed (PID 0x0D)"""
        # Response: Speed = 65 km/h
        data = bytes([0x41, 0x0D, 0x41])
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        param = message.parameters[0]
        self.assertEqual(param.name, "vehicle_speed")
        self.assertEqual(param.value, 65.0)
        self.assertEqual(param.unit, "km/h")
    
    def test_decode_coolant_temp(self):
        """Test decoding coolant temperature (PID 0x05)"""
        # Response: Temp = 90°C
        # Formula: A - 40
        # 90 + 40 = 130 = 0x82
        data = bytes([0x41, 0x05, 0x82])
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        param = message.parameters[0]
        self.assertEqual(param.name, "coolant_temp")
        self.assertEqual(param.value, 90.0)
        self.assertEqual(param.unit, "celsius")
    
    def test_decode_throttle_position(self):
        """Test decoding throttle position (PID 0x11)"""
        # Response: Throttle = 50%
        # Formula: (A * 100) / 255
        # 50% = 127.5 ≈ 0x80
        data = bytes([0x41, 0x11, 0x80])
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        param = message.parameters[0]
        self.assertEqual(param.name, "throttle_position")
        self.assertAlmostEqual(param.value, 50.2, places=1)
        self.assertEqual(param.unit, "percent")
    
    def test_decode_fuel_level(self):
        """Test decoding fuel level (PID 0x2F)"""
        # Response: Fuel = 75%
        # Formula: (A * 100) / 255
        data = bytes([0x41, 0x2F, 0xBF])  # 0xBF ≈ 75%
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        param = message.parameters[0]
        self.assertEqual(param.name, "fuel_level")
        self.assertAlmostEqual(param.value, 75.3, places=1)
        self.assertEqual(param.unit, "percent")
    
    def test_decode_mode_03_request(self):
        """Test decoding Mode 03 request (Show Stored DTCs)"""
        data = bytes([0x03])
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        self.assertEqual(message.mode, 0x03)
        self.assertEqual(message.mode_name, "SHOW_STORED_DTCS")
        self.assertFalse(message.is_response)
    
    def test_decode_mode_03_response_single_dtc(self):
        """Test decoding Mode 03 response with single DTC"""
        # Response with 1 DTC: P0301
        # P0301 = 0x0301 = 0000 0011 0000 0001
        data = bytes([0x43, 0x01, 0x03, 0x01])
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        self.assertTrue(message.is_response)
        self.assertEqual(len(message.dtcs), 1)
        self.assertEqual(message.dtcs[0], "P0301")
    
    def test_decode_mode_03_response_multiple_dtcs(self):
        """Test decoding Mode 03 response with multiple DTCs"""
        # Response with 2 DTCs: P0301, P0420
        data = bytes([0x43, 0x02, 0x03, 0x01, 0x04, 0x20])
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        self.assertEqual(len(message.dtcs), 2)
        self.assertEqual(message.dtcs[0], "P0301")
        self.assertEqual(message.dtcs[1], "P0420")
    
    def test_decode_dtc_powertrain(self):
        """Test decoding powertrain DTC (P-code)"""
        # P0301 = 0x0301
        dtc_bytes = bytes([0x03, 0x01])
        dtc_code = self.decoder._decode_dtc(dtc_bytes)
        self.assertEqual(dtc_code, "P0301")
    
    def test_decode_dtc_chassis(self):
        """Test decoding chassis DTC (C-code)"""
        # C0123 = 0x4123
        dtc_bytes = bytes([0x41, 0x23])
        dtc_code = self.decoder._decode_dtc(dtc_bytes)
        self.assertEqual(dtc_code, "C0123")
    
    def test_decode_dtc_body(self):
        """Test decoding body DTC (B-code)"""
        # B1234 = 0x8234
        dtc_bytes = bytes([0x82, 0x34])
        dtc_code = self.decoder._decode_dtc(dtc_bytes)
        self.assertEqual(dtc_code, "B1234")
    
    def test_decode_dtc_network(self):
        """Test decoding network DTC (U-code)"""
        # U0100 = 0xC100
        dtc_bytes = bytes([0xC1, 0x00])
        dtc_code = self.decoder._decode_dtc(dtc_bytes)
        self.assertEqual(dtc_code, "U0100")
    
    def test_decode_pid_value_rpm(self):
        """Test direct PID value decoding for RPM"""
        data = bytes([0x27, 0x10])  # 2500 RPM
        value = self.decoder.decode_pid_value(0x0C, data)
        self.assertEqual(value, 2500.0)
    
    def test_decode_pid_value_speed(self):
        """Test direct PID value decoding for speed"""
        data = bytes([0x41])  # 65 km/h
        value = self.decoder.decode_pid_value(0x0D, data)
        self.assertEqual(value, 65.0)
    
    def test_decode_unknown_pid(self):
        """Test decoding unknown PID"""
        data = bytes([0x41, 0xFF, 0x00])  # Unknown PID 0xFF
        message = self.decoder.decode_message(data)
        
        self.assertIsNotNone(message)
        self.assertEqual(len(message.parameters), 0)  # No parameters decoded
    
    def test_decode_empty_message(self):
        """Test decoding empty message"""
        data = bytes([])
        message = self.decoder.decode_message(data)
        self.assertIsNone(message)
    
    def test_decode_short_message(self):
        """Test decoding message that's too short"""
        data = bytes([0x41])  # Only mode, no PID
        message = self.decoder.decode_message(data)
        self.assertIsNone(message)
    
    def test_get_pid_info(self):
        """Test getting PID information"""
        info = self.decoder.get_pid_info(0x0C)
        
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "engine_rpm")
        self.assertEqual(info["unit"], "rpm")
        self.assertEqual(info["bytes"], 2)
    
    def test_get_pid_info_unknown(self):
        """Test getting info for unknown PID"""
        info = self.decoder.get_pid_info(0xFF)
        self.assertIsNone(info)
    
    def test_message_to_dict(self):
        """Test converting OBD2Message to dictionary"""
        data = bytes([0x41, 0x0C, 0x27, 0x10])
        message = self.decoder.decode_message(data)
        
        message_dict = message.to_dict()
        self.assertIn("mode", message_dict)
        self.assertIn("mode_name", message_dict)
        self.assertIn("is_response", message_dict)
        self.assertIn("parameters", message_dict)


class TestOBD2Poller(unittest.TestCase):
    """Test OBD-II Poller"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = {
            "obd2": {
                "enabled": True,
                "polling_interval_ms": 1000,
                "pids": [
                    {"name": "engine_rpm", "pid": "0x0C", "interval_ms": 100},
                    {"name": "vehicle_speed", "pid": "0x0D", "interval_ms": 200},
                    {"name": "coolant_temp", "pid": "0x05", "interval_ms": 500}
                ]
            }
        }
        self.poller = OBD2Poller(self.config)
    
    def test_initialization(self):
        """Test poller initialization"""
        self.assertEqual(len(self.poller.pid_configs), 3)
        self.assertFalse(self.poller._running)
    
    def test_pid_config_loading(self):
        """Test PID configuration loading"""
        pid_configs = self.poller.pid_configs
        
        # Check first PID
        self.assertEqual(pid_configs[0].pid, 0x0C)
        self.assertEqual(pid_configs[0].name, "engine_rpm")
        self.assertEqual(pid_configs[0].interval_ms, 100)
        self.assertTrue(pid_configs[0].enabled)
    
    def test_should_poll(self):
        """Test PID polling decision"""
        pid_config = PIDConfig(
            pid=0x0C,
            name="test",
            interval_ms=100,
            enabled=True,
            last_poll_time=0.0
        )
        
        # Should poll immediately
        self.assertTrue(pid_config.should_poll(time.time()))
        
        # Update last poll time
        pid_config.last_poll_time = time.time()
        
        # Should not poll immediately
        self.assertFalse(pid_config.should_poll(time.time()))
        
        # Should poll after interval
        time.sleep(0.11)  # Wait 110ms
        self.assertTrue(pid_config.should_poll(time.time()))
    
    def test_enable_disable_pid(self):
        """Test enabling and disabling PIDs"""
        # Disable PID
        result = self.poller.disable_pid(0x0C)
        self.assertTrue(result)
        
        # Check it's disabled
        pid_config = next(p for p in self.poller.pid_configs if p.pid == 0x0C)
        self.assertFalse(pid_config.enabled)
        
        # Enable PID
        result = self.poller.enable_pid(0x0C)
        self.assertTrue(result)
        self.assertTrue(pid_config.enabled)
    
    def test_set_interval(self):
        """Test setting PID interval"""
        result = self.poller.set_interval(0x0C, 500)
        self.assertTrue(result)
        
        pid_config = next(p for p in self.poller.pid_configs if p.pid == 0x0C)
        self.assertEqual(pid_config.interval_ms, 500)
    
    def test_set_invalid_interval(self):
        """Test setting invalid interval"""
        # Too short
        result = self.poller.set_interval(0x0C, 50)
        self.assertFalse(result)
        
        # Too long
        result = self.poller.set_interval(0x0C, 10000)
        self.assertFalse(result)
    
    def test_add_pid(self):
        """Test adding new PID"""
        initial_count = len(self.poller.pid_configs)
        
        self.poller.add_pid(0x11, "throttle_position", 300)
        
        self.assertEqual(len(self.poller.pid_configs), initial_count + 1)
        
        # Check new PID
        pid_config = next(p for p in self.poller.pid_configs if p.pid == 0x11)
        self.assertEqual(pid_config.name, "throttle_position")
        self.assertEqual(pid_config.interval_ms, 300)
    
    def test_remove_pid(self):
        """Test removing PID"""
        initial_count = len(self.poller.pid_configs)
        
        result = self.poller.remove_pid(0x0C)
        self.assertTrue(result)
        
        self.assertEqual(len(self.poller.pid_configs), initial_count - 1)
    
    def test_get_stats(self):
        """Test getting poller statistics"""
        stats = self.poller.get_stats()
        
        self.assertIn("running", stats)
        self.assertIn("total_pids", stats)
        self.assertIn("enabled_pids", stats)
        self.assertIn("pids", stats)
        
        self.assertEqual(stats["total_pids"], 3)
        self.assertEqual(stats["enabled_pids"], 3)
    
    def test_callback_invocation(self):
        """Test callback is invoked during polling"""
        polled_pids = []
        
        def callback(pid):
            polled_pids.append(pid)
        
        self.poller.set_callback(callback)
        self.poller.start()
        
        # Wait for some polls
        time.sleep(0.3)
        
        self.poller.stop()
        
        # Should have polled some PIDs
        self.assertGreater(len(polled_pids), 0)


if __name__ == '__main__':
    unittest.main()
