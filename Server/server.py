import socket
import sys
import time
import struct
from collections import deque
from typing import Any, Deque, Dict, Tuple

from ConsoleColor import console
from constants import *
from logger import Logger


class Server:

    def __init__(self, host: str, port: int, csvLogDir: str):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False
        self.startTime = time.time()

        self.unitMap: Dict[int, Dict[str, Any]] = {}
        self.unitSeed = 1
        self.macIndex: Dict[str, int] = {}

        self.rollover = 65536
        self.replayBufferSize = 512
        self.lastTimeoutSweep = self.startTime

        self.scribe = Logger(csvLogDir, "server_log")

        console.log.green(f"[Initialization] Booting server...")

        if not self.scribe.start(self.startTime):
            console.log.red("[Initialization] FATAL: Could not start CSV logger.")
            sys.exit(1)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)

        try:
            self.sock.bind((self.host, self.port))
            console.log.green(f"[Initialization] Server loaded and started. Binding to {self.host}:{self.port}.")
        except OSError as bindError:
            console.log.red(f"[Initialization] FATAL: Could not bind to port {self.port}. {bindError}")
            self.scribe.close()
            sys.exit(1)

        console.log.blue(f"[IDLE] Server is now in IDLE state, waiting for packets...")
        self.running = True

    def run(self):

        if not self.sock:
            console.log.red("[Server Error] Server not started. Call start() first.")
            return

        try:
            while self.running:
                self._pollSocket()

        except KeyboardInterrupt:
            console.log.yellow("\n[Shutdown] Keyboard interrupt received.")
        finally:
            self.stop()

    def _pollSocket(self) -> None:
        """Process a single receive/timeout cycle."""
        if not self.sock:
            return

        self.observeTimeouts()

        try:
            packetBlob, origin = self.sock.recvfrom(MAX_PACKET_SIZE)
        except socket.timeout:
            return
        except socket.error as sockError:
            console.log.red(f"[Socket Error] Failure during recvfrom: {sockError}")
            return

        ingressEpoch = time.time()
        self.ingestPacket(packetBlob, origin, ingressEpoch)

    def ingestPacket(self, packetBlob: bytes, origin: Tuple[str, int], ingressEpoch: float):

        if len(packetBlob) < HEADER_SIZE:
            console.log.yellow(f"[Packet Error] Runt packet received from {origin}. Discarding.")
            return

        try:
            headerBlob, bodyBlob = self._splitPacket(packetBlob)
            version, msgType, deviceId, seqNum, timestampOffset, payloadLen = self._interpretHeader(headerBlob)
        except struct.error as parseError:
            console.log.red(f"[Packet Error] Could not parse header from {origin}. {parseError}. Discarding.")
            return

        if version != PROTOCOL_VERSION:
            console.log.yellow(f"[Packet Error] Wrong protocol version {version} from {origin}. Discarding.")
            return

        if len(bodyBlob) != payloadLen:
            console.log.yellow(
                f"[Packet Error] Payload length mismatch from {origin}. Header says {payloadLen}, got {len(bodyBlob)}. Discarding."
            )
            return

        if msgType == MSG_STARTUP:
            self.primeDevice(bodyBlob, origin)
        else:
            self.trackTelemetry(
                (deviceId, msgType, seqNum, timestampOffset, payloadLen),
                bodyBlob,
                origin,
                ingressEpoch
            )

    def _splitPacket(self, packetBlob: bytes) -> Tuple[bytes, bytes]:
        """Separate header and payload sections from the raw datagram."""
        return packetBlob[:HEADER_SIZE], packetBlob[HEADER_SIZE:]

    def _interpretHeader(self, headerBlob: bytes) -> Tuple[int, int, int, int, int, int]:
        """Decode the telemetry header fields."""
        verMsgType, deviceId, _flagBits, seqNum, timestampOffset, payloadLen = struct.unpack(
            HEADER_FORMAT, headerBlob
        )
        version = (verMsgType >> 4) & 0x0F
        msgType = verMsgType & 0x0F
        return version, msgType, deviceId, seqNum, timestampOffset, payloadLen

    def primeDevice(self, payload: bytes, origin: Tuple[str, int]):
        console.log.blue(f"[STARTUP] Received STARTUP request from {origin}.")

        try:
            macRepr = ":".join(f"{b:02X}" for b in payload)
        except struct.error:
            macRepr = "INVALID_MAC"

        staleId = self.macIndex.get(macRepr)
        if staleId is not None:
            console.log.yellow(
                f"[STARTUP] Device at {origin} already registered as DeviceID {staleId} with MAC {macRepr}. Ignoring."
            )
            return

        boundEntry = next(((idx, profile) for idx, profile in self.unitMap.items() if profile['bind_addr'] == origin), None)
        if boundEntry is not None:
            existingId = boundEntry[0]
            console.log.yellow(
                f"[STARTUP] Endpoint {origin} already bound to DeviceID {existingId}. Rejecting duplicate registration."
            )
            return

        freshId = self._nextUnitId()

        self.unitMap[freshId] = {
            'bind_addr': origin,
            'mac_tag': macRepr,
            'head_seq': None,
            'base_time': 0,
            'last_seen': time.time(),
            'last_activity': None,
            'interval_history': deque(maxlen=32),
            'packet_count': 0,
            'last_gap': False,
            'signal_value': 0,
            'missing_seq': set(),
            'seen_set': set(),
            'seen_queue': deque(),
            'timeout_reported': False
        }

        console.log.blue(f"[STARTUP] Assigning DeviceID {freshId} to {origin} - MAC: {macRepr}.")

        self.macIndex[macRepr] = freshId

        try:
            ackHeader = struct.pack(
                HEADER_FORMAT,
                (PROTOCOL_VERSION << 4) | MSG_STARTUP_ACK,
                freshId,
                0,
                0,
                0,
                2
            )
            ackPayload = struct.pack('!H', freshId)

            self.sock.sendto(ackHeader + ackPayload, origin)
            console.log.green(f"[STARTUP_ACK] Sent ACK with DeviceID {freshId} to {origin}.")

        except socket.error as e:
            console.log.red(f"[Socket Error] Could not send STARTUP_ACK to {origin}. {e}")

    def trackTelemetry(self, metaTuple: tuple, payload: bytes, origin: Tuple[str, int], ingressEpoch: float):
        deviceId, msgType, seqNum, timestampOffset, payloadLen = metaTuple

        if deviceId not in self.unitMap:
            console.log.yellow(f"[Packet Error] Received packet from unknown DeviceID {deviceId} at {origin}. Discarding.")
            self._sendRegistrationHint(origin, deviceId)
            return

        state = self.unitMap[deviceId]

        duplicateFlag, gapFlag, delayedFlag = self._classifySequence(deviceId, seqNum, state)

        baseTime = state['base_time']
        fullTimestamp = baseTime + timestampOffset

        self.scribe.log_packet(
            deviceId,
            seqNum,
            fullTimestamp,
            ingressEpoch,
            duplicateFlag,
            gapFlag,
            delayedFlag
        )

        if duplicateFlag:
            return

        priorActivity = state.get('last_activity')

        state['last_seen'] = time.time()
        state['last_activity'] = ingressEpoch
        state['last_gap'] = gapFlag
        state['timeout_reported'] = False

        if delayedFlag:
            return

        state['packet_count'] = state.get('packet_count', 0) + 1
        self._recordInterval(state, ingressEpoch, priorActivity)

        try:
            if msgType == MSG_TIME_SYNC:
                baseTimeVal = struct.unpack('!I', payload)[0]
                state['base_time'] = baseTimeVal
                console.log.blue(f"[TIME_SYNC] DeviceID {deviceId} set base time to {time.ctime(baseTimeVal)}.")

            elif msgType == MSG_KEYFRAME:
                for slot in range(0, payloadLen, 2):
                    valueBe = int(struct.unpack('!h', payload[slot:slot + 2])[0])
                    state['signal_value'] = valueBe

            elif msgType == MSG_DATA_DELTA:
                for slot in range(0, payloadLen, 1):
                    deltaVal = int(struct.unpack('!b', payload[slot:slot + 1])[0])
                    oldValue = state['signal_value']
                    newValue = oldValue + deltaVal
                    state['signal_value'] = newValue

            elif msgType == MSG_HEARTBEAT:
                console.log.blue(f"[HEARTBEAT] Liveness ping from DeviceID {deviceId}.")

            else:
                console.log.yellow(f"[Packet Error] Unknown message type {msgType} from DeviceID {deviceId}. Discarding.")

        except struct.error as payloadError:
            console.log.red(f"[Payload Error] Could not parse payload for msg {msgType} from DeviceID {deviceId}. {payloadError}")
        except IOError as ioError:
            console.log.red(f"[CSV Error] Failed to write to CSV file. {ioError}")

    def stop(self):

        console.log.yellow("[Shutdown] Server shutting down...")
        self.running = False
        if self.scribe:
            self.scribe.close()
        if self.sock:
            self.sock.close()
            console.log.yellow("[Shutdown] Socket closed. Server offline.")

    def observeTimeouts(self):
        now = time.time()
        if now - self.lastTimeoutSweep < 1.5:
            return

        self.lastTimeoutSweep = now

        for deviceId, deviceProfile in list(self.unitMap.items()):
            lastTouch = deviceProfile.get('last_activity')
            if lastTouch is None:
                lastTouch = deviceProfile.get('last_seen', 0)

            if deviceProfile.get('packet_count', 0) < 10:
                continue

            idleSpan = now - lastTouch
            recentSpans = deviceProfile.get('interval_history')
            ceiling, avgInterval = self._deriveTimeout(recentSpans)
            if ceiling is None:
                continue

            if idleSpan >= ceiling:
                if deviceProfile.get('timeout_reported'):
                    continue
                self._flagTimeout(deviceId, deviceProfile, idleSpan, ceiling, avgInterval)

    def _flagTimeout(self, deviceId: int, deviceProfile: Dict[str, Any], idleSpan: float, ceiling: float, avgInterval: float) -> None:
        deviceProfile['timeout_reported'] = True
        intervalNote = f"{avgInterval:.2f}s" if avgInterval else "n/a"
        console.log.red(
            f"[Timeout] DeviceID {deviceId} idle for {idleSpan:.1f}s at {deviceProfile.get('bind_addr')} (interval {intervalNote}, threshold {ceiling:.1f}s, last gap: {deviceProfile.get('last_gap')})."
        )

    def _nextUnitId(self) -> int:
        value = self.unitSeed
        self.unitSeed += 1
        return value

    def _trimSeenQueue(self, deviceState: Dict[str, Any]) -> None:
        """Keep the duplicate filter bounded by evicting stale entries."""
        queueRef = deviceState['seen_queue']
        while len(queueRef) > self.replayBufferSize:
            retiredSeq = queueRef.popleft()
            if retiredSeq not in deviceState['missing_seq'] and retiredSeq != deviceState['head_seq']:
                deviceState['seen_set'].discard(retiredSeq)

    def _sendRegistrationHint(self, origin: Tuple[str, int], deviceId: int) -> None:
        """Send a gentle nudge to clients that forgot to register."""
        if not self.sock:
            return

        try:
            ackHeader = struct.pack(
                HEADER_FORMAT,
                (PROTOCOL_VERSION << 4) | MSG_STARTUP_ACK,
                0,
                0,
                0,
                2
            )
            ackPayload = struct.pack('!H', 0)
            self.sock.sendto(ackHeader + ackPayload, origin)
            console.log.blue(
                f"[STARTUP_ACK] Sent re-registration hint to {origin} for unknown DeviceID {deviceId}."
            )
        except socket.error as exc:
            console.log.red(f"[Socket Error] Could not notify {origin} of missing registration. {exc}")

    def _recordInterval(self, deviceState: Dict[str, Any], ingressEpoch: float, priorActivity: float | None) -> None:
        """Update rolling interval statistics used for timeouts."""
        if priorActivity is None:
            return

        intervalGap = ingressEpoch - priorActivity
        if intervalGap <= 0:
            return

        history = deviceState.get('interval_history')
        if history is not None:
            history.append(intervalGap)

    def _deriveTimeout(self, history: Deque[float] | None) -> Tuple[float | None, float | None]:
        """Derive timeout thresholds from recent inter-arrival spans."""
        if not history:
            return None, None

        totalSpan = 0.0
        sampleCount = 0
        for sample in history:
            totalSpan += sample
            sampleCount += 1

        if sampleCount == 0:
            return None, None

        avgInterval = totalSpan / sampleCount
        if avgInterval <= 0:
            return None, None

        return avgInterval * 10.0, avgInterval

    def _classifySequence(self, deviceId: int, seqNum: int, state: Dict[str, Any]) -> Tuple[bool, bool, bool]:
        duplicateFlag = False
        gapFlag = False
        delayedFlag = False

        headSeq = state['head_seq']

        if headSeq is None:
            state['head_seq'] = seqNum
            state['seen_set'].add(seqNum)
            state['seen_queue'].append(seqNum)
            return duplicateFlag, gapFlag, delayedFlag

        if seqNum in state['seen_set']:
            console.log.yellow(f"[Duplicate] Duplicate packet SeqNum {seqNum} from DeviceID {deviceId}. Suppressing.")
            duplicateFlag = True
        else:
            forwardStep = (seqNum - headSeq) % self.rollover
            backwardStep = (headSeq - seqNum) % self.rollover

            if 0 < forwardStep < self.rollover // 2:
                if forwardStep > 1:
                    missingTotal = 0
                    probeSeq = (headSeq + 1) % self.rollover
                    while probeSeq != seqNum:
                        if probeSeq not in state['missing_seq']:
                            state['missing_seq'].add(probeSeq)
                            missingTotal += 1
                        probeSeq = (probeSeq + 1) % self.rollover
                    if missingTotal > 0:
                        console.log.red(
                            f"[Gap Detect] Packet loss for DeviceID {deviceId}. Missing {missingTotal} packet(s) before SeqNum {seqNum}."
                        )
                        gapFlag = True
                state['head_seq'] = seqNum
            elif 0 < backwardStep < self.rollover // 2:
                if seqNum in state['missing_seq']:
                    state['missing_seq'].discard(seqNum)
                    delayedFlag = True
                    console.log.blue(
                        f"[Delayed] Recovered delayed packet SeqNum {seqNum} for DeviceID {deviceId}."
                    )
                else:
                    duplicateFlag = True
                    console.log.yellow(
                        f"[Duplicate] Late packet SeqNum {seqNum} from DeviceID {deviceId} already processed. Suppressing."
                    )
            else:
                duplicateFlag = True
                console.log.yellow(f"[Duplicate] Out-of-window packet SeqNum {seqNum} from DeviceID {deviceId}. Suppressing.")

        if not duplicateFlag:
            state['seen_set'].add(seqNum)
            state['seen_queue'].append(seqNum)
            self._trimSeenQueue(state)

        return duplicateFlag, gapFlag, delayedFlag