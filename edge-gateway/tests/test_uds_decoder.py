"""
Unit tests for UDS Decoder Service
"""
import unittest
from services.uds_decoder import UDSDecoder, UDSMessage, DTCInfo, UDSService
from services.uds_validator import UDSValidator, ValidationResult


class TestUDSDecoder(unittest.TestCase):
    """Test UDS Decoder"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.decoder = UDSDecoder()
        self.ecu_address = 0x7E0
    
    def test_decode_tester_present_request(self):
        """Test decoding Tester Present request (Service 0x3E)"""
        # Tester Present with sub-function 0x00
        data = bytes([0x3E, 0x00])
        message = self.decoder.decode_message(data, self.ecu_address)
        
        self.assertIsNotNone(message)
        self.assertEqual(message.service_id, 0x3E)
        self.assertEqual(message.service_name, "TESTER_PRESENT")
        self.assertFalse(message.is_response)
        self.assertEqual(message.ecu_address, self.ecu_address)
    
    def test_decode_tester_present_response(self):
        """Test decoding Tester Present response"""
        # Positive response to Tester Present (0x3E + 0x40 = 0x7E)
        data = bytes([0x7E, 0x00])
        message = self.decoder.decode_message(data, self.ecu_address)
        
        self.assertIsNotNone(message)
        self.assertEqual(message.service_id, 0x3E)
        self.assertTrue(message.is_response)
    
    def test_decode_read_data_by_identifier_request(self):
        """Test decoding Read Data By Identifier request (Service 0x22)"""
        # Read VIN (data identifier 0xF190)
        data = bytes([0x22, 0xF1, 0x90])
        message = self.decoder.decode_message(data, self.ecu_address)
        
        self.assertIsNotNone(message)
        self.assertEqual(message.service_id, 0x22)
        self.assertEqual(message.service_name, "READ_DATA_BY_IDENTIFIER")
        self.assertEqual(message.data_identifier, 0xF190)
        self.assertFalse(message.is_response)
    
    def test_decode_read_data_by_identifier_response_vin(self):
        """Test decoding Read Data By Identifier response with VIN"""
        # Response with VIN
        vin = b"1HGBH41JXMN109186"
        data = bytes([0x62, 0xF1, 0x90]) + vin
        message = self.decoder.decode_message(data, self.ecu_address)
        
        self.assertIsNotNone(message)
        self.assertTrue(message.is_response)
        self.assertEqual(message.data_identifier, 0xF190)
        self.assertIn("vin", message.decoded_data)
        self.assertEqual(message.decoded_data["vin"], "1HGBH41JXMN109186")
    
    def test_decode_read_dtc_information_request(self):
        """Test decoding Read DTC Information request (Service 0x19)"""
        # Report DTC by status mask (sub-function 0x02)
        data = bytes([0x19, 0x02, 0xFF])  # All DTCs
        message = self.decoder.decode_message(data, self.ecu_address)
        
        self.assertIsNotNone(message)
        self.assertEqual(message.service_id, 0x19)
        self.assertEqual(message.service_name, "READ_DTC_INFORMATION")
        self.assertFalse(message.is_response)
    
    def test_decode_read_dtc_information_response(self):
        """Test decoding Read DTC Information response with DTCs"""
        # Response with 2 DTCs
        # DTC P0301 (Cylinder 1 Misfire) with status 0x08
        # DTC P0420 (Catalyst System Efficiency) with status 0x48
        data = bytes([
            0x59, 0x02,  # Positive response to service 0x19, sub-function 0x02
            0xFF,  # Status availability mask
            0x01, 0x03, 0x01, 0x08,  # P0301, status 0x08
            0x01, 0x04, 0x20, 0x48   # P0420, status 0x48
        ])
        message = self.decoder.decode_message(data, self.ecu_address)
        
        self.assertIsNotNone(message)
        self.assertTrue(message.is_response)
        self.assertIsNotNone(message.dtc_info)
        self.assertEqual(len(message.dtc_info), 2)
        
        # Check first DTC
        dtc1 = message.dtc_info[0]
        self.assertEqual(dtc1.code, "P0301")
        self.assertEqual(dtc1.status_byte, 0x08)
        
        # Check second DTC
        dtc2 = message.dtc_info[1]
        self.assertEqual(dtc2.code, "P0420")
        self.assertEqual(dtc2.status_byte, 0x48)
    
    def test_decode_dtc_code_powertrain(self):
        """Test decoding powertrain DTC code"""
        # P0301 = 0x010301
        dtc_bytes = bytes([0x01, 0x03, 0x01])
        dtc_code = self.decoder._decode_dtc_code(dtc_bytes)
        self.assertEqual(dtc_code, "P0301")
    
    def test_decode_dtc_code_chassis(self):
        """Test decoding chassis DTC code"""
        # C0123 = 0x410123
        dtc_bytes = bytes([0x41, 0x01, 0x23])
        dtc_code = self.decoder._decode_dtc_code(dtc_bytes)
        self.assertEqual(dtc_code, "C0123")
    
    def test_decode_dtc_code_body(self):
        """Test decoding body DTC code"""
        # B1234 = 0x812340
        dtc_bytes = bytes([0x81, 0x23, 0x40])
        dtc_code = self.decoder._decode_dtc_code(dtc_bytes)
        self.assertEqual(dtc_code, "B1234")
    
    def test_get_dtc_severity_critical(self):
        """Test DTC severity classification - critical"""
        # Status byte with critical severity (0x80)
        severity = self.decoder._get_dtc_severity(0x88)
        self.assertEqual(severity, "critical")
    
    def test_get_dtc_severity_high(self):
        """Test DTC severity classification - high"""
        # Status byte with high severity (0x40)
        severity = self.decoder._get_dtc_severity(0x48)
        self.assertEqual(severity, "high")
    
    def test_get_dtc_severity_medium(self):
        """Test DTC severity classification - medium"""
        # Status byte with medium severity (0x20)
        severity = self.decoder._get_dtc_severity(0x28)
        self.assertEqual(severity, "medium")
    
    def test_get_dtc_severity_low(self):
        """Test DTC severity classification - low"""
        # Status byte with low severity
        severity = self.decoder._get_dtc_severity(0x08)
        self.assertEqual(severity, "low")
    
    def test_decode_empty_message(self):
        """Test decoding empty message"""
        data = bytes([])
        message = self.decoder.decode_message(data, self.ecu_address)
        self.assertIsNone(message)
    
    def test_decode_unknown_service(self):
        """Test decoding message with unknown service ID"""
        # Service ID 0xFF is not defined
        data = bytes([0xFF, 0x00])
        message = self.decoder.decode_message(data, self.ecu_address)
        
        self.assertIsNotNone(message)
        self.assertIn("UNKNOWN_SERVICE", message.service_name)
    
    def test_validate_message_valid(self):
        """Test validating a valid UDS message"""
        data = bytes([0x3E, 0x00])
        is_valid = self.decoder.validate_message(data)
        self.assertTrue(is_valid)
    
    def test_validate_message_invalid_empty(self):
        """Test validating empty message"""
        data = bytes([])
        is_valid = self.decoder.validate_message(data)
        self.assertFalse(is_valid)
    
    def test_message_to_dict(self):
        """Test converting UDS message to dictionary"""
        data = bytes([0x3E, 0x00])
        message = self.decoder.decode_message(data, self.ecu_address)
        
        message_dict = message.to_dict()
        self.assertIn("service_id", message_dict)
        self.assertIn("service_name", message_dict)
        self.assertIn("ecu_address", message_dict)
        self.assertIn("is_response", message_dict)


class TestUDSValidator(unittest.TestCase):
    """Test UDS Validator"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.validator = UDSValidator()
        self.ecu_address = 0x7E0
    
    def test_validate_valid_tester_present(self):
        """Test validating valid Tester Present message"""
        data = bytes([0x3E, 0x00])
        result = self.validator.validate_message(data, self.ecu_address)
        
        self.assertTrue(result.is_valid)
        self.assertIsNone(result.error_code)
    
    def test_validate_empty_message(self):
        """Test validating empty message"""
        data = bytes([])
        result = self.validator.validate_message(data, self.ecu_address)
        
        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, "EMPTY_MESSAGE")
    
    def test_validate_invalid_service_id(self):
        """Test validating message with invalid service ID"""
        data = bytes([0xFF, 0x00])  # 0xFF is not a valid service
        result = self.validator.validate_message(data, self.ecu_address)
        
        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, "INVALID_SERVICE_ID")
    
    def test_validate_message_too_short(self):
        """Test validating message that's too short"""
        # Read DTC Information requires at least 2 bytes
        data = bytes([0x19])
        result = self.validator.validate_message(data, self.ecu_address)
        
        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, "INVALID_LENGTH")
    
    def test_validate_negative_response(self):
        """Test validating negative response"""
        # Negative response: service not supported
        data = bytes([0x7F, 0x22, 0x11])  # Service 0x22 not supported
        result = self.validator.validate_message(data, self.ecu_address)
        
        self.assertTrue(result.is_valid)
        self.assertTrue(len(result.warnings) > 0)
        self.assertIn("Negative response", result.warnings[0])
    
    def test_validate_read_data_by_identifier(self):
        """Test validating Read Data By Identifier message"""
        data = bytes([0x22, 0xF1, 0x90])
        result = self.validator.validate_message(data, self.ecu_address)
        
        self.assertTrue(result.is_valid)
    
    def test_validate_read_data_by_identifier_too_short(self):
        """Test validating Read Data By Identifier that's too short"""
        data = bytes([0x22, 0xF1])  # Missing second byte of data identifier
        result = self.validator.validate_message(data, self.ecu_address)
        
        self.assertFalse(result.is_valid)
    
    def test_log_invalid_message(self):
        """Test logging invalid message"""
        data = bytes([0xFF, 0x00])
        result = self.validator.validate_message(data, self.ecu_address)
        
        # Should not raise exception
        with self.assertLogs(level='ERROR') as log:
            self.validator.log_invalid_message(data, self.ecu_address, result)
            self.assertTrue(len(log.output) > 0)
    
    def test_validation_result_to_dict(self):
        """Test converting validation result to dictionary"""
        result = ValidationResult(
            is_valid=False,
            error_code="TEST_ERROR",
            error_message="Test error message",
            warnings=["Warning 1"]
        )
        
        result_dict = result.to_dict()
        self.assertFalse(result_dict["is_valid"])
        self.assertEqual(result_dict["error_code"], "TEST_ERROR")
        self.assertEqual(len(result_dict["warnings"]), 1)


if __name__ == '__main__':
    unittest.main()
