import math
import socket
import sys
import time
import struct
from enum import Enum
from collections import deque
from typing import Any, Deque, Dict, Tuple
from xmlrpc.client import FastParser

from ConsoleColor import console
from constants import *
from logger import Logger

class DeviceStatus(Enum):
    IDLE = 0
    ACTIVE = 1
    TIMEOUT = 2
    DOWN = 3

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
        self.csvLogger = Logger(csvLogDir, "server_log")

        console.log.green(f"[Initialization] Booting server...")

        if self.csvLogger.start(self.startTime) is False:
            console.log.red("[Initialization] FATAL: Could not start CSV logger.")
            sys.exit(1)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)

        try:

            self.sock.bind((self.host, self.port))
            console.log.green(f"[Initialization] Server loaded and started. Binding to {self.host}:{self.port}.")

        except OSError as bindError:

            console.log.red(f"[Initialization] FATAL: Could not bind to port {self.port}. {bindError}")
            self.csvLogger.close()
            sys.exit(1)

        console.log.blue(f"[IDLE] Server is now in IDLE state, waiting for packets...")
        self.running = True

    def run(self):

        if self.sock is None:
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

        if self.sock is None:
            return

        self.timeoutObserver()
        try:

            incomingPacket, origin = self.sock.recvfrom(MAX_PACKET_SIZE)

        except socket.timeout:
            return

        except socket.error as sockError:

            console.log.red(f"[Socket Error] Failure during recvfrom: {sockError}")
            return

        ingressTime = time.time()
        self.processPacket(incomingPacket, origin, ingressTime)

    def processPacket(self, incommingPakcet: bytes, origin: Tuple[str, int], ingressTime: float):

        if len(incommingPakcet) < HEADER_SIZE:
            console.log.yellow(f"[Packet Error] Runt packet received from {origin}. Discarding.")
            return

        try:
            headerBlob, bodyBlob = incommingPakcet[:HEADER_SIZE], incommingPakcet[HEADER_SIZE:]

            verMsgType, deviceId, seqNum, timestampOffset, payloadLen = struct.unpack(
                HEADER_FORMAT, headerBlob
            )

            version = (verMsgType >> 4) & (0xFF)
            msgType = (verMsgType & (0xF))

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
            self.deviceRegisteration(bodyBlob, origin)
        
        elif msgType == MSG_SHUTDOWN:
            deviceProfile = self.unitMap.get(deviceId)
        
            if deviceProfile:
                deviceProfile['status'] = DeviceStatus.DOWN
        
            console.log.blue(f"[SHUTDOWN] Received SHUTDOWN from DeviceID {deviceId} at {origin}. Ignoring.")
        
        elif msgType == MSG_BATCHED_DATA:
        
            self.BatchTelemetry((deviceId, msgType, seqNum, timestampOffset, payloadLen), bodyBlob, origin, ingressTime )
        elif msgType == MSG_TIME_SYNC:
            state = self.unitMap.get(deviceId)
            try:
                baseTimeVal = struct.unpack('!I', bodyBlob)[0]
                state['base_time'] = baseTimeVal
                console.log.blue(f"[TIME_SYNC] DeviceID {deviceId} set base time to {time.ctime(baseTimeVal)}.")
                duplicateFlag, gapFlag, delayedFlag = self.classifyPacket(deviceId, seqNum, state)
                self.csvLogger.log_packet(deviceId, seqNum, baseTimeVal + timestampOffset, ingressTime, duplicateFlag, gapFlag,
                                          delayedFlag)
            except struct.error as timeError:
                console.log.red(f"[Payload Error] Could not parse TIME_SYNC payload from DeviceID {deviceId}. {timeError}")
        else:
            self.trackTelemetry(
                (deviceId, msgType, seqNum, timestampOffset, payloadLen), bodyBlob, origin, ingressTime )
            
            
    def deviceRegisteration(self, payload: bytes, origin: Tuple[str, int]):
        
        console.log.blue(f"[STARTUP] Received STARTUP request from {origin}.")

        try:
            macRepr = ":".join(f"{b:02X}" for b in payload[:6])
        
        except struct.error:
            macRepr = "INVALID_MAC"

        staleId = self.macIndex.get(macRepr)
        
        if staleId:
        
            staleProfile = self.unitMap.get(staleId)
        
            if staleProfile and staleProfile['status'] == DeviceStatus.DOWN:

                console.log.blue(f"[STARTUP] Device at {origin} with MAC {macRepr} previously marked. Re-registering.")
        
                try:
        
                    ackHeader = struct.pack(HEADER_FORMAT,(PROTOCOL_VERSION << 4) | MSG_STARTUP_ACK,staleId, int(False), int(False), 4)
                    ackPayload = struct.pack('!HH', staleId, staleProfile['current_seq'])
                    
                    self.sock.sendto(ackHeader + ackPayload, origin)
                    
                    console.log.green(f"[STARTUP_ACK] Sent ACK with DeviceID {staleId} to {origin}.")

                except socket.error as e:
                    console.log.red(f"[Socket Error] Could not send STARTUP_ACK to {origin}: {e}")

                return
            
            console.log.yellow( f"[STARTUP] Device at {origin} already registered as DeviceID {staleId} with MAC {macRepr}. Ignoring.")
            return

        boundEntry = next(((idx, profile) for idx, profile in self.unitMap.items() if profile['bind_addr'] == origin), None)

        if boundEntry is not None:

            existingId = boundEntry[0]
            console.log.yellow( f"[STARTUP] Endpoint {origin} already bound to DeviceID {existingId} and didn't timeout. Rejecting duplicate registration.")
            return

        freshId = self.unitSeed
        self.unitSeed += 1

        self.unitMap[freshId] = {
            'bind_addr': origin,
            'mac_tag': macRepr,
            'current_seq': None,

            'base_time': 0,
            'last_seen': time.time(),
            'last_activity': None,
            'interval_history': deque(maxlen=32),

            'packet_count': 0,

            'last_gap': False,
            'signal_value': 0,
            'missing_seq': set(),
            'seen_set': set(),
            'seen_count': {},

            'status': DeviceStatus.IDLE,
            'seen_queue': deque(),
            'timeout_reported': False,

            'batching': False if len(payload) < 7 else True,
            'batch_size': 1 if len(payload) < 7 else struct.unpack('!B', payload[6:7])[0]
        }

        console.log.blue(f"[STARTUP] Assigning DeviceID {freshId} to {origin} - MAC: {macRepr}.")

        self.macIndex[macRepr] = freshId

        try:

            ackHeader = struct.pack( HEADER_FORMAT,(PROTOCOL_VERSION << 4) | MSG_STARTUP_ACK, freshId, 0, 0,2)
            ackPayload = struct.pack('!H', freshId)
            self.sock.sendto(ackHeader + ackPayload, origin)

            console.log.green(f"[STARTUP_ACK] Sent ACK with DeviceID {freshId} to {origin}.")

        except socket.error as e:
            console.log.red(f"[Socket Error] Could not send STARTUP_ACK to {origin}. {e}")


    def BatchTelemetry(self, metaTuple: tuple, payload: bytes, origin: Tuple[str, int], ingressTime: float):

        deviceId, msgType, seqNum, timestampOffset, payloadLen = metaTuple

        if self.unitMap.__contains__(deviceId) is False:
            console.log.yellow(f"[Packet Error] Received batch packet from unknown DeviceID {deviceId} at {origin}. Discarding.")
            return

        offset, delta_counter,keyframe_counter = 0,0,0

        while offset < payloadLen:

            try:
                entryOffset = struct.unpack('!h', payload[offset:offset + 2])[0]
                entryType= struct.unpack('!B', payload[offset + 2:offset + 3])[0]

                if entryType == MSG_KEYFRAME:

                    value = struct.unpack('!h', payload[offset + 3:offset + 5])[0]
                    entryPayload = struct.pack('!h', value)
                    entryMeta = (deviceId, entryType, seqNum, timestampOffset + entryOffset, 2)

                    self.trackTelemetry(entryMeta, entryPayload, origin, ingressTime)
                    offset += 5
                    keyframe_counter += 1

                elif entryType == MSG_DATA_DELTA:

                    value = struct.unpack('!b', payload[offset + 3:offset + 4])[0]
                    entryPayload = struct.pack('!b', value)
                    entryMeta = (deviceId, entryType, seqNum, timestampOffset + entryOffset, 1)

                    self.trackTelemetry(entryMeta, entryPayload, origin, ingressTime)
                    offset += 4
                    delta_counter += 1

                else:
                    console.log.red(f"[Packet Error] Unknown message type {entryType} in batch from DeviceID {deviceId}. Skipping entry.")
                    break

            except struct.error as payloadError:
                console.log.red(f"[Payload Error] Could not parse batch entry from DeviceID {deviceId}. {payloadError}")
                break

        console.log.blue(f"[BATCH] Processed batch from DeviceID {deviceId}: {keyframe_counter} keyframes, {delta_counter} deltas.")


    def trackTelemetry(self, metaTuple: tuple, payload: bytes, origin: Tuple[str, int], ingressTime: float):

        deviceId, msgType, seqNum, timestampOffset, payloadLen = metaTuple

        if self.unitMap.__contains__(deviceId) is False:

            console.log.yellow(f"[Packet Error] Received packet from unknown DeviceID {deviceId} at {origin}. Discarding.")
            return

        state = self.unitMap[deviceId]

        duplicateFlag, gapFlag, delayedFlag = self.classifyPacket(deviceId, seqNum, state)
        baseTime = state['base_time']
        fullTimestamp = baseTime + timestampOffset

        self.csvLogger.log_packet(deviceId, seqNum, fullTimestamp, ingressTime, duplicateFlag, gapFlag,delayedFlag )

        if duplicateFlag:
            return

        priorActivity = state.get('last_activity')

        state['last_seen'] = time.time()
        state['last_activity'] = ingressTime
        state['last_gap'] = gapFlag
        state['timeout_reported'] = False

        if delayedFlag:
            return

        state['packet_count'] = state.get('packet_count', 0) + 1

        if priorActivity is None or priorActivity >= ingressTime:
            return

        if state.get('interval_history'):
            state.get('interval_history').append(ingressTime - priorActivity)

        try:
            if msgType == MSG_KEYFRAME:
            
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
       
        if self.csvLogger:
            self.csvLogger.close()
       
        if self.sock:
            self.sock.close()
            console.log.yellow("[Shutdown] Socket closed. Server offline.")

    def timeoutObserver(self):
        now = time.time()
       
        if self.lastTimeoutSweep - now >= 1.5:
            return
        self.lastTimeoutSweep = now
       
        for deviceId, deviceProfile in list(self.unitMap.items()):
            
            last = deviceProfile.get('last_activity')
            
            if not last:
                last = deviceProfile.get('last_seen', 0)
            
            if deviceProfile.get('packet_count', 0) < 10:
                continue
            
            idleTime = now - last
            recentSpans = deviceProfile.get('interval_history')

            calculateTimeout = lambda recentSpans: (None, None) if recentSpans is None else (
                (None, None) if len(recentSpans) == 0 or sum(recentSpans) <= 0 else
                (sum(recentSpans) * 10.0 / len(recentSpans), sum(recentSpans) / len(recentSpans))
            )

            ceiling, avgInterval = calculateTimeout(recentSpans)
            
            if not ceiling:
                continue
            
            else:
                
                if ((idleTime >= ceiling) and (deviceProfile.get('status') != DeviceStatus.DOWN) and (deviceProfile.get('status') != DeviceStatus.TIMEOUT)):
                    
                    if deviceProfile.get('timeout_reported'):
                        continue
                    
                    else:
                    
                        deviceProfile['timeout_reported'] = True
                        intervalNote = f"{avgInterval:.2f}s" if avgInterval else "n/a"
                        console.log.red(f"[Timeout] DeviceID {deviceId} idle for {idleTime:.1f}s at {deviceProfile.get('bind_addr')} (interval {intervalNote}, threshold {ceiling:.1f}s, last gap: {deviceProfile.get('last_gap')}).")

    def classifyPacket(self, deviceId: int, seqNum: int, state: Dict[str, Any]) -> Tuple[bool, bool, bool]:
        duplicateFlag,gapFlag,delayedFlag = False,False,False

        headSeq = state['current_seq']
        if headSeq is None:
            state['current_seq'] = seqNum
            state['seen_set'].add(seqNum)
            state['seen_queue'].append(seqNum)
            return (duplicateFlag, gapFlag, delayedFlag)

        if seqNum in state['seen_set']:

            if state['batching']:
                if state['seen_count'].get(seqNum) is None:
                    state['seen_count'][seqNum] = 1

                if state['seen_count'][seqNum] <= state['batch_size']:
                    state['seen_count'][seqNum] = state['seen_count'][seqNum] + 1
                    return (False, gapFlag, delayedFlag)

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

                        console.log.red(f"[Gap Detect] Packet loss for DeviceID {deviceId}. Missing {missingTotal} packet(s) before SeqNum {seqNum}.")
                        gapFlag = True

                state['current_seq'] = seqNum

            elif 0 < backwardStep < self.rollover // 2:

                if seqNum in state['missing_seq']:

                    state['missing_seq'].discard(seqNum)
                    delayedFlag = True
                    console.log.blue(f"[Delayed] Recovered delayed packet SeqNum {seqNum} for DeviceID {deviceId}.")

                else:

                    duplicateFlag = True
                    console.log.yellow(f"[Duplicate] Late packet SeqNum {seqNum} from DeviceID {deviceId} already processed. Suppressing.")

            else:
                duplicateFlag = True
                console.log.yellow(f"[Duplicate] Out-of-window packet SeqNum {seqNum} from DeviceID {deviceId}. Suppressing.")

        if duplicateFlag is False:

            state['seen_set'].add(seqNum)
            state['seen_queue'].append(seqNum)
            queueRef = state['seen_queue']

            while len(queueRef) > self.replayBufferSize:

                retiredSeq = queueRef.popleft()
                if retiredSeq not in state['missing_seq'] and not retiredSeq == state['current_seq']:
                    state['seen_set'].discard(retiredSeq)

        return duplicateFlag, gapFlag, delayedFlag