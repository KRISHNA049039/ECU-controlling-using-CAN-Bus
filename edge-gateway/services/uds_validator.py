"""
UDS Message Validator

Validates UDS messages against ISO 14229 specification.
"""
import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """UDS message validation result"""
    is_valid: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    warnings: list = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "is_valid": self.is_valid,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "warnings": self.warnings
        }


class UDSValidator:
    """Validates UDS messages according to ISO 14229"""
    
    # Valid service IDs (ISO 14229-1)
    VALID_SERVICE_IDS = {
        0x10, 0x11, 0x14, 0x19, 0x22, 0x23, 0x24, 0x27, 0x28, 0x2A,
        0x2C, 0x2E, 0x2F, 0x31, 0x34, 0x35, 0x36, 0x37, 0x38, 0x3D,
        0x3E, 0x83, 0x84, 0x85, 0x86, 0x87
    }
    
    # Minimum message lengths for each service
    MIN_MESSAGE_LENGTHS = {
        0x10: 2,  # Diagnostic Session Control
        0x11: 2,  # ECU Reset
        0x14: 4,  # Clear Diagnostic Information
        0x19: 2,  # Read DTC Information
        0x22: 3,  # Read Data By Identifier
        0x23: 4,  # Read Memory By Address
        0x27: 2,  # Security Access
        0x2E: 4,  # Write Data By Identifier
        0x3E: 2,  # Tester Present
        0x31: 4,  # Routine Control
    }
    
    # Negative response codes
    NEGATIVE_RESPONSE_CODES = {
        0x10: "General Reject",
        0x11: "Service Not Supported",
        0x12: "Sub-Function Not Supported",
        0x13: "Incorrect Message Length Or Invalid Format",
        0x14: "Response Too Long",
        0x21: "Busy Repeat Request",
        0x22: "Conditions Not Correct",
        0x24: "Request Sequence Error",
        0x25: "No Response From Sub-Net Component",
        0x26: "Failure Prevents Execution Of Requested Action",
        0x31: "Request Out Of Range",
        0x33: "Security Access Denied",
        0x35: "Invalid Key",
        0x36: "Exceed Number Of Attempts",
        0x37: "Required Time Delay Not Expired",
        0x70: "Upload Download Not Accepted",
        0x71: "Transfer Data Suspended",
        0x72: "General Programming Failure",
        0x73: "Wrong Block Sequence Counter",
        0x78: "Request Correctly Received - Response Pending",
        0x7E: "Sub-Function Not Supported In Active Session",
        0x7F: "Service Not Supported In Active Session",
    }
    
    def __init__(self):
        """Initialize UDS validator"""
        logger.info("Initialized UDS validator")
    
    def validate_message(self, data: bytes, ecu_address: int) -> ValidationResult:
        """
        Validate UDS message format
        
        Args:
            data: Raw message data
            ecu_address: ECU address
            
        Returns:
            ValidationResult
        """
        # Check if data is empty
        if not data or len(data) == 0:
            return ValidationResult(
                is_valid=False,
                error_code="EMPTY_MESSAGE",
                error_message="Message data is empty"
            )
        
        service_id = data[0]
        is_response = service_id >= 0x40
        
        # Check for negative response
        if service_id == 0x7F:
            return self._validate_negative_response(data)
        
        # Get actual service ID
        actual_service_id = service_id - 0x40 if is_response else service_id
        
        # Validate service ID
        if actual_service_id not in self.VALID_SERVICE_IDS:
            logger.warning(
                f"Invalid UDS service ID: {hex(service_id)} from ECU {hex(ecu_address)}"
            )
            return ValidationResult(
                is_valid=False,
                error_code="INVALID_SERVICE_ID",
                error_message=f"Unknown service ID: {hex(service_id)}"
            )
        
        # Validate message length
        min_length = self.MIN_MESSAGE_LENGTHS.get(actual_service_id, 1)
        if len(data) < min_length:
            return ValidationResult(
                is_valid=False,
                error_code="INVALID_LENGTH",
                error_message=f"Message too short: {len(data)} bytes (minimum: {min_length})"
            )
        
        # Validate checksum if present (last byte)
        checksum_result = self._validate_checksum(data)
        
        # Service-specific validation
        service_validation = self._validate_service_specific(actual_service_id, data, is_response)
        
        # Combine results
        if not service_validation.is_valid:
            return service_validation
        
        # Add checksum warnings if any
        if checksum_result and not checksum_result.is_valid:
            service_validation.warnings.append(checksum_result.error_message)
        
        return service_validation
    
    def _validate_negative_response(self, data: bytes) -> ValidationResult:
        """
        Validate negative response message
        
        Args:
            data: Raw message data
            
        Returns:
            ValidationResult
        """
        if len(data) < 3:
            return ValidationResult(
                is_valid=False,
                error_code="INVALID_NEGATIVE_RESPONSE",
                error_message="Negative response too short"
            )
        
        requested_service = data[1]
        response_code = data[2]
        
        response_desc = self.NEGATIVE_RESPONSE_CODES.get(
            response_code,
            f"Unknown response code: {hex(response_code)}"
        )
        
        logger.info(
            f"Negative response for service {hex(requested_service)}: "
            f"{response_desc} (code: {hex(response_code)})"
        )
        
        return ValidationResult(
            is_valid=True,
            warnings=[f"Negative response: {response_desc}"]
        )
    
    def _validate_checksum(self, data: bytes) -> Optional[ValidationResult]:
        """
        Validate message checksum (if present)
        
        Args:
            data: Raw message data
            
        Returns:
            ValidationResult or None if no checksum
        """
        # ISO 14229 doesn't mandate checksums at application layer
        # This is typically handled by lower layers (CAN, etc.)
        # We'll implement a simple XOR checksum validation as an example
        
        # For now, return None (no checksum validation)
        return None
    
    def _validate_service_specific(
        self,
        service_id: int,
        data: bytes,
        is_response: bool
    ) -> ValidationResult:
        """
        Perform service-specific validation
        
        Args:
            service_id: UDS service ID
            data: Raw message data
            is_response: Whether this is a response message
            
        Returns:
            ValidationResult
        """
        warnings = []
        
        # Service 0x19: Read DTC Information
        if service_id == 0x19:
            if len(data) < 2:
                return ValidationResult(
                    is_valid=False,
                    error_code="INVALID_DTC_REQUEST",
                    error_message="Read DTC Information requires sub-function"
                )
            
            sub_function = data[1]
            valid_sub_functions = [0x01, 0x02, 0x03, 0x04, 0x06, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E]
            
            if sub_function not in valid_sub_functions:
                warnings.append(f"Unknown DTC sub-function: {hex(sub_function)}")
        
        # Service 0x22: Read Data By Identifier
        elif service_id == 0x22:
            if len(data) < 3:
                return ValidationResult(
                    is_valid=False,
                    error_code="INVALID_READ_DATA",
                    error_message="Read Data By Identifier requires data identifier"
                )
            
            # Data identifier should be 2 bytes
            if not is_response and len(data) != 3:
                warnings.append("Unexpected message length for Read Data By Identifier request")
        
        # Service 0x3E: Tester Present
        elif service_id == 0x3E:
            if len(data) < 2:
                return ValidationResult(
                    is_valid=False,
                    error_code="INVALID_TESTER_PRESENT",
                    error_message="Tester Present requires sub-function"
                )
            
            sub_function = data[1] & 0x7F  # Remove suppress bit
            if sub_function != 0x00:
                warnings.append(f"Non-standard Tester Present sub-function: {hex(sub_function)}")
        
        # Service 0x2E: Write Data By Identifier
        elif service_id == 0x2E:
            if len(data) < 4:
                return ValidationResult(
                    is_valid=False,
                    error_code="INVALID_WRITE_DATA",
                    error_message="Write Data By Identifier requires data identifier and data"
                )
        
        return ValidationResult(is_valid=True, warnings=warnings)
    
    def log_invalid_message(self, data: bytes, ecu_address: int, validation_result: ValidationResult) -> None:
        """
        Log invalid message with raw payload
        
        Args:
            data: Raw message data
            ecu_address: ECU address
            validation_result: Validation result
        """
        logger.error(
            f"Invalid UDS message from ECU {hex(ecu_address)}: "
            f"{validation_result.error_message} "
            f"(code: {validation_result.error_code})"
        )
        logger.error(f"Raw payload: {data.hex()}")
        
        # Log first few bytes for debugging
        if len(data) > 0:
            logger.error(f"Service ID: {hex(data[0])}")
        if len(data) > 1:
            logger.error(f"Sub-function/Data: {data[1:].hex()}")
