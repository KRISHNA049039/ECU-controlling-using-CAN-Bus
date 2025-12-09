"""
OBD-II Protocol Decoder Service

Decodes OBD-II (On-Board Diagnostics II) messages per SAE J1979 standard.
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import struct

logger = logging.getLogger(__name__)


class OBD2Mode(Enum):
    """OBD-II Mode identifiers"""
    SHOW_CURRENT_DATA = 0x01
    SHOW_FREEZE_FRAME = 0x02
    SHOW_STORED_DTCS = 0x03
    CLEAR_DTCS = 0x04
    TEST_RESULTS_O2 = 0x05
    TEST_RESULTS_OTHER = 0x06
    SHOW_PENDING_DTCS = 0x07
    CONTROL_OPERATION = 0x08
    REQUEST_VEHICLE_INFO = 0x09
    PERMANENT_DTCS = 0x0A


@dataclass
class OBD2Parameter:
    """OBD-II parameter with value and unit"""
    name: str
    pid: int
    value: float
    unit: str
    raw_value: bytes
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "pid": hex(self.pid),
            "value": self.value,
            "unit": self.unit,
            "raw_value": self.raw_value.hex()
        }


@dataclass
class OBD2Message:
    """Parsed OBD-II Message"""
    mode: int
    mode_name: str
    pid: Optional[int] = None
    parameters: List[OBD2Parameter] = None
    dtcs: List[str] = None
    is_response: bool = False
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = []
        if self.dtcs is None:
            self.dtcs = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "mode": hex(self.mode),
            "mode_name": self.mode_name,
            "is_response": self.is_response
        }
        
        if self.pid is not None:
            result["pid"] = hex(self.pid)
        
        if self.parameters:
            result["parameters"] = [p.to_dict() for p in self.parameters]
        
        if self.dtcs:
            result["dtcs"] = self.dtcs
        
        return result


class OBD2Decoder:
    """OBD-II Protocol Decoder"""
    
    # PID definitions with conversion formulas
    PID_DEFINITIONS = {
        0x0C: {
            "name": "engine_rpm",
            "unit": "rpm",
            "bytes": 2,
            "formula": lambda data: ((data[0] * 256) + data[1]) / 4
        },
        0x0D: {
            "name": "vehicle_speed",
            "unit": "km/h",
            "bytes": 1,
            "formula": lambda data: data[0]
        },
        0x05: {
            "name": "coolant_temp",
            "unit": "celsius",
            "bytes": 1,
            "formula": lambda data: data[0] - 40
        },
        0x11: {
            "name": "throttle_position",
            "unit": "percent",
            "bytes": 1,
            "formula": lambda data: (data[0] * 100) / 255
        },
        0x2F: {
            "name": "fuel_level",
            "unit": "percent",
            "bytes": 1,
            "formula": lambda data: (data[0] * 100) / 255
        },
        0x0F: {
            "name": "intake_air_temp",
            "unit": "celsius",
            "bytes": 1,
            "formula": lambda data: data[0] - 40
        },
        0x10: {
            "name": "maf_flow_rate",
            "unit": "g/s",
            "bytes": 2,
            "formula": lambda data: ((data[0] * 256) + data[1]) / 100
        },
        0x04: {
            "name": "engine_load",
            "unit": "percent",
            "bytes": 1,
            "formula": lambda data: (data[0] * 100) / 255
        },
        0x0E: {
            "name": "timing_advance",
            "unit": "degrees",
            "bytes": 1,
            "formula": lambda data: (data[0] / 2) - 64
        },
        0x42: {
            "name": "control_module_voltage",
            "unit": "volts",
            "bytes": 2,
            "formula": lambda data: ((data[0] * 256) + data[1]) / 1000
        }
    }
    
    def __init__(self):
        """Initialize OBD-II decoder"""
        logger.info("Initialized OBD-II decoder")
    
    def decode_message(self, data: bytes) -> Optional[OBD2Message]:
        """
        Decode OBD-II message
        
        Args:
            data: Raw message data
            
        Returns:
            OBD2Message if valid, None otherwise
        """
        if not data or len(data) < 2:
            logger.warning("Invalid OBD-II message: insufficient data")
            return None
        
        mode = data[0]
        is_response = mode >= 0x40
        
        # Get actual mode (remove response bit)
        actual_mode = mode - 0x40 if is_response else mode
        
        # Get mode name
        mode_name = self._get_mode_name(actual_mode)
        
        message = OBD2Message(
            mode=actual_mode,
            mode_name=mode_name,
            is_response=is_response
        )
        
        # Decode based on mode
        if actual_mode == OBD2Mode.SHOW_CURRENT_DATA.value:
            self._decode_mode_01(message, data, is_response)
        elif actual_mode == OBD2Mode.SHOW_STORED_DTCS.value:
            self._decode_mode_03(message, data, is_response)
        
        return message
    
    def _get_mode_name(self, mode: int) -> str:
        """Get mode name from mode number"""
        try:
            return OBD2Mode(mode).name
        except ValueError:
            return f"UNKNOWN_MODE_{hex(mode)}"
    
    def _decode_mode_01(self, message: OBD2Message, data: bytes, is_response: bool) -> None:
        """
        Decode Mode 01 (Show Current Data)
        
        Args:
            message: OBD2Message to populate
            data: Raw message data
            is_response: Whether this is a response
        """
        if len(data) < 2:
            return
        
        pid = data[1]
        message.pid = pid
        
        if not is_response:
            # Request message
            logger.debug(f"OBD-II Mode 01 request for PID {hex(pid)}")
            return
        
        # Response message - decode parameter value
        if len(data) < 3:
            logger.warning(f"Mode 01 response too short for PID {hex(pid)}")
            return
        
        # Get PID definition
        pid_def = self.PID_DEFINITIONS.get(pid)
        if not pid_def:
            logger.warning(f"Unknown PID: {hex(pid)}")
            return
        
        # Extract data bytes
        data_bytes = data[2:2 + pid_def["bytes"]]
        if len(data_bytes) < pid_def["bytes"]:
            logger.warning(f"Insufficient data bytes for PID {hex(pid)}")
            return
        
        # Apply conversion formula
        try:
            value = pid_def["formula"](data_bytes)
            
            parameter = OBD2Parameter(
                name=pid_def["name"],
                pid=pid,
                value=round(value, 2),
                unit=pid_def["unit"],
                raw_value=data_bytes
            )
            
            message.parameters.append(parameter)
            logger.debug(f"Decoded {parameter.name}: {parameter.value} {parameter.unit}")
            
        except Exception as e:
            logger.error(f"Error decoding PID {hex(pid)}: {e}")
    
    def _decode_mode_03(self, message: OBD2Message, data: bytes, is_response: bool) -> None:
        """
        Decode Mode 03 (Show Stored DTCs)
        
        Args:
            message: OBD2Message to populate
            data: Raw message data
            is_response: Whether this is a response
        """
        if not is_response:
            # Request message
            logger.debug("OBD-II Mode 03 request for stored DTCs")
            return
        
        if len(data) < 2:
            return
        
        # First byte after mode is number of DTCs
        num_dtcs = data[1]
        
        # Each DTC is 2 bytes
        offset = 2
        dtcs = []
        
        while offset + 1 < len(data) and len(dtcs) < num_dtcs:
            dtc_bytes = data[offset:offset+2]
            dtc_code = self._decode_dtc(dtc_bytes)
            if dtc_code and dtc_code != "P0000":  # Skip empty DTCs
                dtcs.append(dtc_code)
            offset += 2
        
        message.dtcs = dtcs
        logger.debug(f"Decoded {len(dtcs)} DTCs: {dtcs}")
    
    def _decode_dtc(self, dtc_bytes: bytes) -> Optional[str]:
        """
        Decode 2-byte DTC to standard format
        
        Args:
            dtc_bytes: 2 bytes representing DTC
            
        Returns:
            DTC code string (e.g., "P0301")
        """
        if len(dtc_bytes) != 2:
            return None
        
        # First 2 bits determine prefix
        first_byte = dtc_bytes[0]
        prefix_code = (first_byte >> 6) & 0x03
        
        prefixes = {0: 'P', 1: 'C', 2: 'B', 3: 'U'}
        prefix = prefixes.get(prefix_code, 'P')
        
        # Next 2 bits are first digit
        first_digit = (first_byte >> 4) & 0x03
        
        # Next 4 bits are second digit
        second_digit = first_byte & 0x0F
        
        # Second byte contains third and fourth digits
        third_digit = (dtc_bytes[1] >> 4) & 0x0F
        fourth_digit = dtc_bytes[1] & 0x0F
        
        return f"{prefix}{first_digit}{second_digit}{third_digit}{fourth_digit}"
    
    def decode_pid_value(self, pid: int, data: bytes) -> Optional[float]:
        """
        Decode raw PID data to engineering value
        
        Args:
            pid: PID identifier
            data: Raw data bytes
            
        Returns:
            Decoded value or None
        """
        pid_def = self.PID_DEFINITIONS.get(pid)
        if not pid_def:
            return None
        
        if len(data) < pid_def["bytes"]:
            return None
        
        try:
            return pid_def["formula"](data[:pid_def["bytes"]])
        except Exception as e:
            logger.error(f"Error decoding PID {hex(pid)}: {e}")
            return None
    
    def get_pid_info(self, pid: int) -> Optional[Dict[str, Any]]:
        """
        Get PID information
        
        Args:
            pid: PID identifier
            
        Returns:
            Dictionary with PID info or None
        """
        pid_def = self.PID_DEFINITIONS.get(pid)
        if not pid_def:
            return None
        
        return {
            "pid": hex(pid),
            "name": pid_def["name"],
            "unit": pid_def["unit"],
            "bytes": pid_def["bytes"]
        }
