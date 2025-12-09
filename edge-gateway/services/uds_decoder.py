"""
UDS Protocol Decoder Service

Decodes Unified Diagnostic Services (ISO 14229) messages.
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import struct

logger = logging.getLogger(__name__)


class UDSService(Enum):
    """UDS Service Identifiers"""
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    SECURITY_ACCESS = 0x27
    COMMUNICATION_CONTROL = 0x28
    TESTER_PRESENT = 0x3E
    ACCESS_TIMING_PARAMETER = 0x83
    SECURED_DATA_TRANSMISSION = 0x84
    CONTROL_DTC_SETTING = 0x85
    RESPONSE_ON_EVENT = 0x86
    LINK_CONTROL = 0x87
    READ_DATA_BY_IDENTIFIER = 0x22
    READ_MEMORY_BY_ADDRESS = 0x23
    READ_SCALING_DATA_BY_IDENTIFIER = 0x24
    READ_DATA_BY_PERIODIC_IDENTIFIER = 0x2A
    DYNAMICALLY_DEFINE_DATA_IDENTIFIER = 0x2C
    WRITE_DATA_BY_IDENTIFIER = 0x2E
    WRITE_MEMORY_BY_ADDRESS = 0x3D
    CLEAR_DIAGNOSTIC_INFORMATION = 0x14
    READ_DTC_INFORMATION = 0x19
    INPUT_OUTPUT_CONTROL_BY_IDENTIFIER = 0x2F
    ROUTINE_CONTROL = 0x31
    REQUEST_DOWNLOAD = 0x34
    REQUEST_UPLOAD = 0x35
    TRANSFER_DATA = 0x36
    REQUEST_TRANSFER_EXIT = 0x37
    REQUEST_FILE_TRANSFER = 0x38


class DTCSeverity(Enum):
    """DTC Severity Levels"""
    NO_SEVERITY = 0x00
    MAINTENANCE_ONLY = 0x20
    CHECK_AT_NEXT_HALT = 0x40
    CHECK_IMMEDIATELY = 0x80


@dataclass
class DTCInfo:
    """Diagnostic Trouble Code Information"""
    code: str  # e.g., "P0301"
    status_byte: int
    severity: str
    description: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "code": self.code,
            "status_byte": hex(self.status_byte),
            "severity": self.severity,
            "description": self.description
        }


@dataclass
class UDSMessage:
    """Parsed UDS Message"""
    service_id: int
    service_name: str
    ecu_address: int
    data: bytes
    is_response: bool
    response_code: Optional[int] = None
    dtc_info: Optional[List[DTCInfo]] = None
    data_identifier: Optional[int] = None
    decoded_data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "service_id": hex(self.service_id),
            "service_name": self.service_name,
            "ecu_address": hex(self.ecu_address),
            "data": self.data.hex(),
            "is_response": self.is_response
        }
        
        if self.response_code is not None:
            result["response_code"] = hex(self.response_code)
        
        if self.dtc_info:
            result["dtc_info"] = [dtc.to_dict() for dtc in self.dtc_info]
        
        if self.data_identifier is not None:
            result["data_identifier"] = hex(self.data_identifier)
        
        if self.decoded_data:
            result["decoded_data"] = self.decoded_data
        
        return result


class UDSDecoder:
    """UDS Protocol Decoder"""
    
    # DTC code prefixes
    DTC_PREFIXES = {
        0x0: 'P',  # Powertrain
        0x1: 'C',  # Chassis
        0x2: 'B',  # Body
        0x3: 'U'   # Network
    }
    
    def __init__(self):
        """Initialize UDS decoder"""
        logger.info("Initialized UDS decoder")
    
    def decode_message(self, data: bytes, ecu_address: int) -> Optional[UDSMessage]:
        """
        Decode UDS message
        
        Args:
            data: Raw message data
            ecu_address: ECU address
            
        Returns:
            UDSMessage if valid, None otherwise
        """
        if not data or len(data) < 1:
            logger.warning("Invalid UDS message: empty data")
            return None
        
        service_id = data[0]
        is_response = service_id >= 0x40
        
        # Get actual service ID (remove response bit)
        actual_service_id = service_id - 0x40 if is_response else service_id
        
        # Get service name
        service_name = self._get_service_name(actual_service_id)
        
        message = UDSMessage(
            service_id=actual_service_id,
            service_name=service_name,
            ecu_address=ecu_address,
            data=data,
            is_response=is_response
        )
        
        # Decode based on service type
        if actual_service_id == UDSService.READ_DTC_INFORMATION.value:
            self._decode_read_dtc_information(message, data)
        elif actual_service_id == UDSService.READ_DATA_BY_IDENTIFIER.value:
            self._decode_read_data_by_identifier(message, data)
        elif actual_service_id == UDSService.TESTER_PRESENT.value:
            self._decode_tester_present(message, data)
        
        return message
    
    def _get_service_name(self, service_id: int) -> str:
        """Get service name from ID"""
        try:
            return UDSService(service_id).name
        except ValueError:
            return f"UNKNOWN_SERVICE_{hex(service_id)}"
    
    def _decode_read_dtc_information(self, message: UDSMessage, data: bytes) -> None:
        """
        Decode Read DTC Information (Service 0x19)
        
        Args:
            message: UDSMessage to populate
            data: Raw message data
        """
        if len(data) < 2:
            logger.warning("Invalid Read DTC Information message: insufficient data")
            return
        
        sub_function = data[1]
        
        if not message.is_response:
            message.decoded_data = {"sub_function": hex(sub_function)}
            return
        
        # Parse DTC response
        if sub_function in [0x02, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E]:  # Report DTCs
            dtc_list = []
            
            # Skip service ID, sub-function, and status availability mask
            offset = 3 if len(data) > 2 else 2
            
            # Each DTC is 4 bytes (3 bytes DTC + 1 byte status)
            while offset + 3 < len(data):
                dtc_bytes = data[offset:offset+3]
                status_byte = data[offset+3]
                
                # Decode DTC code
                dtc_code = self._decode_dtc_code(dtc_bytes)
                severity = self._get_dtc_severity(status_byte)
                
                dtc_info = DTCInfo(
                    code=dtc_code,
                    status_byte=status_byte,
                    severity=severity
                )
                dtc_list.append(dtc_info)
                
                offset += 4
            
            message.dtc_info = dtc_list
            logger.debug(f"Decoded {len(dtc_list)} DTCs from UDS message")
    
    def _decode_read_data_by_identifier(self, message: UDSMessage, data: bytes) -> None:
        """
        Decode Read Data By Identifier (Service 0x22)
        
        Args:
            message: UDSMessage to populate
            data: Raw message data
        """
        if len(data) < 3:
            logger.warning("Invalid Read Data By Identifier message: insufficient data")
            return
        
        # Data identifier is 2 bytes
        data_identifier = struct.unpack('>H', data[1:3])[0]
        message.data_identifier = data_identifier
        
        if message.is_response and len(data) > 3:
            # Response contains the data
            response_data = data[3:]
            message.decoded_data = {
                "data_identifier": hex(data_identifier),
                "response_data": response_data.hex(),
                "response_length": len(response_data)
            }
            
            # Try to decode common data identifiers
            if data_identifier == 0xF190:  # VIN
                try:
                    vin = response_data.decode('ascii')
                    message.decoded_data["vin"] = vin
                except Exception:
                    pass
    
    def _decode_tester_present(self, message: UDSMessage, data: bytes) -> None:
        """
        Decode Tester Present (Service 0x3E)
        
        Args:
            message: UDSMessage to populate
            data: Raw message data
        """
        if len(data) < 2:
            return
        
        sub_function = data[1]
        message.decoded_data = {
            "sub_function": hex(sub_function),
            "suppress_positive_response": bool(sub_function & 0x80)
        }
    
    def _decode_dtc_code(self, dtc_bytes: bytes) -> str:
        """
        Decode 3-byte DTC to standard format (e.g., P0301)
        
        Args:
            dtc_bytes: 3 bytes representing DTC
            
        Returns:
            DTC code string
        """
        if len(dtc_bytes) != 3:
            return "INVALID"
        
        # First byte contains prefix and first digit
        first_byte = dtc_bytes[0]
        prefix_code = (first_byte >> 6) & 0x03
        first_digit = (first_byte >> 4) & 0x03
        second_digit = first_byte & 0x0F
        
        # Second and third bytes contain remaining digits
        third_digit = (dtc_bytes[1] >> 4) & 0x0F
        fourth_digit = dtc_bytes[1] & 0x0F
        fifth_digit = (dtc_bytes[2] >> 4) & 0x0F
        
        prefix = self.DTC_PREFIXES.get(prefix_code, 'U')
        
        return f"{prefix}{first_digit}{second_digit}{third_digit}{fourth_digit}"
    
    def _get_dtc_severity(self, status_byte: int) -> str:
        """
        Get DTC severity from status byte
        
        Args:
            status_byte: DTC status byte
            
        Returns:
            Severity string
        """
        severity_bits = status_byte & 0xE0
        
        if severity_bits == DTCSeverity.CHECK_IMMEDIATELY.value:
            return "critical"
        elif severity_bits == DTCSeverity.CHECK_AT_NEXT_HALT.value:
            return "high"
        elif severity_bits == DTCSeverity.MAINTENANCE_ONLY.value:
            return "medium"
        else:
            return "low"
    
    def validate_message(self, data: bytes) -> bool:
        """
        Validate UDS message format
        
        Args:
            data: Raw message data
            
        Returns:
            True if valid, False otherwise
        """
        if not data or len(data) < 1:
            return False
        
        service_id = data[0]
        
        # Check if service ID is valid (either request or response)
        actual_service_id = service_id - 0x40 if service_id >= 0x40 else service_id
        
        try:
            UDSService(actual_service_id)
            return True
        except ValueError:
            # Unknown service ID
            logger.warning(f"Unknown UDS service ID: {hex(service_id)}")
            return False
