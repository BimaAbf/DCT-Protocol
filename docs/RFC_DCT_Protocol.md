# RFC: Data Collection Telemetry (DCT) Protocol

**Document Status:** Informational  
**Version:** 1.0  
**Date:** December 2025  
**Authors:** DCT Protocol Working Group  

---

## Abstract

This document specifies the Data Collection Telemetry (DCT) Protocol, a lightweight, efficient binary protocol designed for real-time telemetry data transmission between IoT devices and centralized data collection servers. The protocol is optimized for low-bandwidth environments and supports features such as delta compression, batching, sequence tracking, and device registration.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Terminology](#2-terminology)
3. [Protocol Overview](#3-protocol-overview)
4. [Message Format](#4-message-format)
5. [Message Types](#5-message-types)
6. [Connection Lifecycle](#6-connection-lifecycle)
7. [Data Transmission](#7-data-transmission)
8. [Batching Mechanism](#8-batching-mechanism)
9. [Sequence Number Handling](#9-sequence-number-handling)
10. [Time Synchronization](#10-time-synchronization)
11. [Error Detection and Recovery](#11-error-detection-and-recovery)
12. [Security Considerations](#12-security-considerations)
13. [IANA Considerations](#13-iana-considerations)
14. [References](#14-references)
15. [Appendix A: Message Type Registry](#appendix-a-message-type-registry)
16. [Appendix B: Example Message Flows](#appendix-b-example-message-flows)

---

## 1. Introduction

### 1.1 Purpose

The Data Collection Telemetry (DCT) Protocol is designed to address the need for efficient, low-overhead telemetry data transmission in resource-constrained environments. Traditional protocols like HTTP/JSON or MQTT introduce significant overhead that may be unacceptable for battery-powered IoT devices or bandwidth-limited networks.

### 1.2 Scope

This specification defines:
- The binary message format for DCT packets
- Message types and their semantics
- Device registration and connection lifecycle
- Data compression techniques (delta encoding, batching)
- Sequence tracking and loss detection mechanisms

### 1.3 Design Goals

| Goal | Description |
|------|-------------|
| **Efficiency** | Minimize packet overhead through binary encoding |
| **Reliability** | Provide mechanisms for detecting packet loss and duplicates |
| **Simplicity** | Keep the protocol simple enough for embedded implementations |
| **Scalability** | Support multiple concurrent device connections |
| **Flexibility** | Support both individual and batched data transmission |

---

## 2. Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

| Term | Definition |
|------|------------|
| **Server** | The centralized data collection endpoint that receives telemetry data |
| **Client** | A device that transmits telemetry data to the server |
| **Device ID** | A 16-bit unique identifier assigned by the server to each client |
| **Keyframe** | A complete value transmission containing the absolute sensor value |
| **Delta** | An incremental value representing the change from the previous value |
| **Batch** | A collection of multiple data updates transmitted in a single packet |
| **Sequence Number** | A 16-bit counter used to detect packet loss and ordering |

---

## 3. Protocol Overview

### 3.1 Transport Layer

DCT operates over UDP (User Datagram Protocol) on a configurable port (default: 5000). UDP is chosen for:
- Lower latency compared to TCP
- Reduced connection overhead
- Suitability for time-series data where occasional loss is acceptable

### 3.2 Architecture

```
┌─────────────────┐                    ┌─────────────────┐
│                 │    UDP Datagrams   │                 │
│   DCT Client    │ ─────────────────► │   DCT Server    │
│   (Device)      │ ◄───────────────── │   (Collector)   │
│                 │    (ACK only for   │                 │
│                 │     STARTUP)       │                 │
└─────────────────┘                    └─────────────────┘
```

### 3.3 Protocol Version

The current protocol version is **0x01** (1). The version is encoded in the high nibble of the first header byte.

---

## 4. Message Format

### 4.1 General Packet Structure

All DCT messages consist of a fixed-size header followed by a variable-length payload.

```
+------------------+------------------+
|      Header      |     Payload      |
|    (8 bytes)     |   (0-192 bytes)  |
+------------------+------------------+
```

### 4.2 Header Format

The header is exactly 8 bytes and uses network byte order (big-endian).

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|Version|  Type |           Device ID                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|        Sequence Number        |         Time Offset           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Payload Len |
+-+-+-+-+-+-+-+
```

| Field | Size | Description |
|-------|------|-------------|
| Version | 4 bits | Protocol version (currently 0x01) |
| Type | 4 bits | Message type identifier |
| Device ID | 16 bits | Server-assigned device identifier |
| Sequence Number | 16 bits | Monotonically increasing packet counter |
| Time Offset | 16 bits | Seconds offset from base time |
| Payload Length | 8 bits | Length of payload in bytes (0-255) |

### 4.3 Binary Encoding Format

The header format string for binary packing is: `!BHHHB`

| Symbol | Meaning | Size |
|--------|---------|------|
| `!` | Network byte order (big-endian) | - |
| `B` | Unsigned char (Version + Type) | 1 byte |
| `H` | Unsigned short (Device ID) | 2 bytes |
| `H` | Unsigned short (Sequence Number) | 2 bytes |
| `H` | Unsigned short (Time Offset) | 2 bytes |
| `B` | Unsigned char (Payload Length) | 1 byte |

**Total Header Size: 8 bytes**

---

## 5. Message Types

### 5.1 Message Type Registry

| Type Code | Name | Direction | Description |
|-----------|------|-----------|-------------|
| 0x01 | MSG_STARTUP | Client → Server | Device registration request |
| 0x02 | MSG_STARTUP_ACK | Server → Client | Registration acknowledgment |
| 0x03 | MSG_TIME_SYNC | Client → Server | Base time synchronization |
| 0x04 | MSG_KEYFRAME | Client → Server | Absolute value transmission |
| 0x05 | MSG_DATA_DELTA | Client → Server | Delta value transmission |
| 0x06 | MSG_HEARTBEAT | Client → Server | Liveness indication |
| 0x07 | MSG_BATCHED_DATA | Client → Server | Batched data transmission |
| 0x08 | MSG_DATA_DELTA_QUANTIZED | Client → Server | Quantized delta (reserved) |
| 0x09 | MSG_KEYFRAME_QUANTIZED | Client → Server | Quantized keyframe (reserved) |
| 0x0A | MSG_BATCHED_DATA_QUANTIZED | Client → Server | Quantized batch (reserved) |
| 0x0B | MSG_SHUTDOWN | Client → Server | Graceful disconnect |
| 0x0C | MSG_BATCH_INCOMPLETE | Client → Server | Partial batch transmission |

### 5.2 MSG_STARTUP (0x01)

**Purpose:** Register a new device with the server.

**Payload Format:**
```
+------------------+------------------+
|   MAC Address    | Batch Size (opt) |
|    (6 bytes)     |    (1 byte)      |
+------------------+------------------+
```

| Field | Size | Description |
|-------|------|-------------|
| MAC Address | 6 bytes | Device's hardware MAC address |
| Batch Size | 1 byte | Optional: number of entries per batch (if batching enabled) |

**Behavior:**
- Client MUST send STARTUP as the first message
- Device ID in header SHOULD be 0x0000
- Server assigns a unique Device ID upon successful registration

### 5.3 MSG_STARTUP_ACK (0x02)

**Purpose:** Acknowledge device registration and provide Device ID.

**Payload Format:**
```
+------------------+------------------+
|    Device ID     | Last Seq (opt)   |
|    (2 bytes)     |   (2 bytes)      |
+------------------+------------------+
```

| Field | Size | Description |
|-------|------|-------------|
| Device ID | 2 bytes | Assigned device identifier |
| Last Seq | 2 bytes | Optional: last known sequence for reconnection |

**Behavior:**
- Server MUST respond with STARTUP_ACK within timeout period
- 2-byte payload indicates new registration
- 4-byte payload indicates re-registration with sequence recovery

### 5.4 MSG_TIME_SYNC (0x03)

**Purpose:** Establish a base timestamp for relative time offsets.

**Payload Format:**
```
+----------------------------------+
|         Base Time (Unix)         |
|            (4 bytes)             |
+----------------------------------+
```

| Field | Size | Description |
|-------|------|-------------|
| Base Time | 4 bytes | Unix timestamp (seconds since epoch) |

**Behavior:**
- Client SHOULD send TIME_SYNC before transmitting data
- Server uses base time to calculate absolute timestamps
- Client SHOULD re-sync periodically (recommended: every 100 packets)

### 5.5 MSG_KEYFRAME (0x04)

**Purpose:** Transmit an absolute sensor value.

**Payload Format:**
```
+------------------+
|      Value       |
|    (2 bytes)     |
+------------------+
```

| Field | Size | Description |
|-------|------|-------------|
| Value | 2 bytes | Signed 16-bit integer (-32768 to 32767) |

**Behavior:**
- MUST be sent at session start
- SHOULD be sent periodically to prevent delta accumulation errors
- Recommended: every 10 data transmissions

### 5.6 MSG_DATA_DELTA (0x05)

**Purpose:** Transmit the change from the previous value.

**Payload Format:**
```
+---------+
|  Delta  |
| (1 byte)|
+---------+
```

| Field | Size | Description |
|-------|------|-------------|
| Delta | 1 byte | Signed 8-bit integer (-128 to 127) |

**Behavior:**
- Used when change magnitude fits in 8 bits
- If delta exceeds ±127, MUST use KEYFRAME instead
- Server reconstructs absolute value by accumulating deltas

### 5.7 MSG_HEARTBEAT (0x06)

**Purpose:** Indicate device liveness without data transmission.

**Payload:** Empty (0 bytes)

**Behavior:**
- Sent when no data change occurs
- Prevents server timeout detection
- Does not increment sequence number when batching is enabled

### 5.8 MSG_BATCHED_DATA (0x07)

**Purpose:** Transmit multiple data points in a single packet.

**Payload Format:**
```
+--------+------+-------+--------+------+-------+-----+
| Offset | Type | Value | Offset | Type | Value | ... |
+--------+------+-------+--------+------+-------+-----+
```

**Entry Format:**
| Field | Size | Description |
|-------|------|-------------|
| Time Offset | 2 bytes | Relative time within batch |
| Entry Type | 1 byte | MSG_KEYFRAME or MSG_DATA_DELTA |
| Value | 1-2 bytes | Delta (1 byte) or Keyframe (2 bytes) |

**Entry Sizes:**
- Delta entry: 4 bytes (2 + 1 + 1)
- Keyframe entry: 5 bytes (2 + 1 + 2)

### 5.9 MSG_SHUTDOWN (0x0B)

**Purpose:** Graceful session termination.

**Payload:** Empty (0 bytes)

**Behavior:**
- Client SHOULD send before disconnecting
- Server marks device as DOWN
- Enables clean session cleanup

---

## 6. Connection Lifecycle

### 6.1 State Diagram

```
                    ┌─────────────┐
                    │    IDLE     │
                    └──────┬──────┘
                           │ STARTUP
                           ▼
                    ┌─────────────┐
                    │  CONNECTING │
                    └──────┬──────┘
                           │ STARTUP_ACK
                           ▼
                    ┌─────────────┐
                    │   ACTIVE    │◄────┐
                    └──────┬──────┘     │ Data Messages
                           │            │
                           ├────────────┘
                           │ Timeout / SHUTDOWN
                           ▼
                    ┌─────────────┐
                    │    DOWN     │
                    └─────────────┘
```

### 6.2 Registration Handshake

```
Client                                Server
  │                                     │
  │──────── STARTUP (MAC) ─────────────►│
  │                                     │ Assign Device ID
  │◄─────── STARTUP_ACK (ID) ───────────│
  │                                     │
  │──────── TIME_SYNC (base) ──────────►│
  │                                     │
  │──────── KEYFRAME (initial) ────────►│
  │                                     │
```

### 6.3 Reconnection Handling

When a device reconnects (same MAC address):
1. Server detects existing MAC in registry
2. Server responds with 4-byte STARTUP_ACK
3. Payload includes: Device ID (2 bytes) + Last Sequence (2 bytes)
4. Client resumes from provided sequence number

---

## 7. Data Transmission

### 7.1 Value Encoding Strategy

```
┌─────────────────────────────────────────────────────┐
│                  Decision Logic                      │
├─────────────────────────────────────────────────────┤
│  IF (packet_count % 10 == 0) THEN                   │
│      SEND KEYFRAME                                   │
│  ELSE IF (abs(delta) > 127) THEN                    │
│      SEND KEYFRAME                                   │
│  ELSE IF (abs(delta) > threshold) THEN              │
│      SEND DATA_DELTA                                 │
│  ELSE                                                │
│      SEND HEARTBEAT                                  │
│  END                                                 │
└─────────────────────────────────────────────────────┘
```

### 7.2 Bandwidth Efficiency

| Message Type | Header | Payload | Total | Efficiency |
|--------------|--------|---------|-------|------------|
| KEYFRAME | 8 bytes | 2 bytes | 10 bytes | 20% payload |
| DATA_DELTA | 8 bytes | 1 byte | 9 bytes | 11% payload |
| HEARTBEAT | 8 bytes | 0 bytes | 8 bytes | 0% payload |
| BATCHED (5 deltas) | 8 bytes | 20 bytes | 28 bytes | 71% payload |

---

## 8. Batching Mechanism

### 8.1 Configuration

Batching is configured during STARTUP by appending a 1-byte batch size to the MAC address payload. A batch size of 1 disables batching.

### 8.2 Batch Assembly

```python
# Batch entry structure
for each data_point:
    offset = current_time - base_time
    if is_keyframe:
        entry = pack('!HBh', offset, MSG_KEYFRAME, value)  # 5 bytes
    else:
        entry = pack('!HBb', offset, MSG_DATA_DELTA, delta)  # 4 bytes
    batch_buffer.append(entry)
    
    if len(batch_buffer) == batch_size:
        send_batch(batch_buffer)
        batch_buffer.clear()
```

### 8.3 Batch Processing (Server)

1. Parse each entry in sequence
2. Reconstruct absolute values from deltas
3. Assign individual timestamps using entry offsets
4. Log each entry with its batch index

---

## 9. Sequence Number Handling

### 9.1 Sequence Space

- 16-bit unsigned integer (0-65535)
- Wraps around at 65536 (rollover)
- Window size: 512 packets for replay detection

### 9.2 Gap Detection Algorithm

```python
def classify_packet(seq_num, state):
    head_seq = state.current_seq
    rollover = 65536
    
    forward_step = (seq_num - head_seq) % rollover
    backward_step = (head_seq - seq_num) % rollover
    
    if forward_step < rollover // 2:
        # Forward sequence
        if forward_step > 1:
            # Gap detected
            mark_missing(range(head_seq + 1, seq_num))
        state.current_seq = seq_num
        return NORMAL
    elif backward_step < rollover // 2:
        # Backward sequence (delayed or duplicate)
        if seq_num in state.missing_set:
            return DELAYED
        else:
            return DUPLICATE
    else:
        return OUT_OF_WINDOW
```

### 9.3 Duplicate Detection

- Server maintains a sliding window of 512 seen sequence numbers
- Packets outside the window are treated as duplicates
- Delayed packets (filling gaps) are logged but not re-processed

---

## 10. Time Synchronization

### 10.1 Two-Tier Timestamp System

| Component | Resolution | Purpose |
|-----------|------------|---------|
| Base Time | 1 second | Unix timestamp anchor |
| Time Offset | 1 second | Relative offset (0-65535s) |

### 10.2 Timestamp Reconstruction

```python
absolute_timestamp = base_time + time_offset
```

### 10.3 Synchronization Frequency

- Initial: Immediately after STARTUP_ACK
- Periodic: Every 100 packets (recommended)
- Maximum offset without re-sync: 65535 seconds (~18 hours)

---

## 11. Error Detection and Recovery

### 11.1 Packet Loss Detection

| Indicator | Detection Method | Server Action |
|-----------|------------------|---------------|
| Sequence Gap | Missing numbers in sequence | Log gap_flag=1 |
| Timeout | No packets for N×average_interval | Mark device TIMEOUT |

### 11.2 Duplicate Handling

- Duplicates are detected via seen_set
- Duplicate packets are logged with duplicate_flag=1
- Value is NOT updated from duplicates

### 11.3 Timeout Calculation

```python
def calculate_timeout(interval_history):
    if len(interval_history) < 10:
        return None  # Insufficient data
    
    avg_interval = sum(interval_history) / len(interval_history)
    timeout_ceiling = avg_interval * 10  # 10x average interval
    
    return timeout_ceiling
```

---

## 12. Security Considerations

### 12.1 Current Limitations

The DCT Protocol version 1.0 does NOT provide:
- Authentication
- Encryption
- Integrity verification

### 12.2 Recommendations

For production deployments, implementers SHOULD:
1. Deploy DCT over VPN or encrypted tunnel
2. Use network-level access controls (firewall, IP whitelisting)
3. Consider DTLS for transport security
4. Implement application-level authentication in future versions

### 12.3 Threat Model

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Eavesdropping | Data exposure | Use VPN/DTLS |
| Spoofing | Fake data injection | MAC-based filtering |
| Replay | Duplicate data | Sequence number tracking |
| DoS | Server overload | Rate limiting |

---

## 13. IANA Considerations

This document does not require any IANA actions. The default port 5000 is used by convention but is configurable.

---

## 14. References

### 14.1 Normative References

- [RFC 768] Postel, J., "User Datagram Protocol", STD 6, RFC 768, August 1980.
- [RFC 2119] Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC 2119, March 1997.

### 14.2 Informative References

- [RFC 3393] Demichelis, C. and P. Chimento, "IP Packet Delay Variation Metric for IP Performance Metrics (IPPM)", RFC 3393, November 2002.
- [RFC 6298] Paxson, V., Allman, M., Chu, J., and M. Sargent, "Computing TCP's Retransmission Timer", RFC 6298, June 2011.

---

## Appendix A: Message Type Registry

| Code | Name | Payload Size | Direction |
|------|------|--------------|-----------|
| 0x01 | MSG_STARTUP | 6-7 bytes | C→S |
| 0x02 | MSG_STARTUP_ACK | 2-4 bytes | S→C |
| 0x03 | MSG_TIME_SYNC | 4 bytes | C→S |
| 0x04 | MSG_KEYFRAME | 2 bytes | C→S |
| 0x05 | MSG_DATA_DELTA | 1 byte | C→S |
| 0x06 | MSG_HEARTBEAT | 0 bytes | C→S |
| 0x07 | MSG_BATCHED_DATA | Variable | C→S |
| 0x08 | MSG_DATA_DELTA_QUANTIZED | 1 byte | C→S |
| 0x09 | MSG_KEYFRAME_QUANTIZED | 2 bytes | C→S |
| 0x0A | MSG_BATCHED_DATA_QUANTIZED | Variable | C→S |
| 0x0B | MSG_SHUTDOWN | 0 bytes | C→S |
| 0x0C | MSG_BATCH_INCOMPLETE | Variable | C→S |

---

## Appendix B: Example Message Flows

### B.1 Normal Session

```
Time   Direction   Message              Payload
────   ─────────   ───────              ───────
0.00   C → S       STARTUP              MAC=AA:BB:CC:DD:EE:FF, Batch=5
0.01   S → C       STARTUP_ACK          DeviceID=1
0.02   C → S       TIME_SYNC            BaseTime=1735049400
0.03   C → S       KEYFRAME             Value=500
0.50   C → S       DATA_DELTA           Delta=+5
1.00   C → S       DATA_DELTA           Delta=-3
1.50   C → S       DATA_DELTA           Delta=+2
2.00   C → S       DATA_DELTA           Delta=+1
2.50   C → S       BATCHED_DATA         [5 entries]
...
60.00  C → S       SHUTDOWN             (empty)
```

### B.2 Reconnection Scenario

```
Time   Direction   Message              Payload
────   ─────────   ───────              ───────
0.00   C → S       STARTUP              MAC=AA:BB:CC:DD:EE:FF
0.01   S → C       STARTUP_ACK          DeviceID=1, LastSeq=150
0.02   C → S       TIME_SYNC            BaseTime=1735049460
0.03   C → S       KEYFRAME             Seq=151, Value=520
```

---

## Authors' Addresses

DCT Protocol Working Group  
Email: dct-protocol@example.com

---

*End of RFC Document*
