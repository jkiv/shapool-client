import asyncio
import binascii
import hashlib
import logging
import json
import os
import sys

from . import shapool

_log = logging.getLogger('shapool-client.stratum')

class StratumClient:

    def __init__(self, host, port):
        self.host = host
        self.port = port

        self._reader = None
        self._writer = None

        self._call_id = 0
        self._extra_nonce_1 = None
        self._extra_nonce_2_size = None

    async def connect(self):
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._call_id = 0

    async def disconnect(self):
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    async def subscribe(self, user_agent):
        await self.call("mining.subscribe", [])
        # TODO not guaranteed a recv() for subscribe call.
        response = await self._recv()

        subscription_details, extra_nonce_1, extra_nonce_2_size = response["result"]

        # TODO handle subscription_details

        # Save subscription params
        self._extra_nonce_1 = binascii.a2b_hex(extra_nonce_1)
        self._extra_nonce_2_size = extra_nonce_2_size

        return response

    async def authorize(self, username, password):
         await self.call("mining.authorize", [username, password])
         response = await self._recv()
         # TODO handle errors
         return response

    async def suggest_difficulty(self, difficulty):
        await self.call("mining.suggest_difficulty", [difficulty])
        response = await self._recv()
        # TODO handle errors
        return response

    async def call(self, method, params):
        payload = {"id": self._call_id, "method": method, "params": params}
        self._call_id += 1
        await self._send(payload)

    async def _send(self, payload):
        payload_json = json.dumps(payload).encode() + b'\n'
        self._writer.write(payload_json)
        await self._writer.drain()

    async def _recv(self):
        message = await self._reader.readline()
        return json.loads(message.strip())

    def _handle_error(self, error, full_message):
        _log.error(f'🤦‍ Stratum Error ({error[0]}): {error[1]}')
        # 20 - Other/Unknown
        # 21 - Job not found(=stale)
        # 22 - Duplicate share
        # 23 - Low difficulty share
        # 24 - Unauthorized worker
        # 25 - Not subscribed

    async def _handle_set_difficulty(self, params, recv_queue):
        difficulty, = params
        _log.info(f'🤹‍ Server asking to set new difficulty: {difficulty=}')
        await recv_queue.put(('set_difficulty', (difficulty,)))

    async def _handle_notify(self, params, recv_queue, shapool_, interrupt_work):
        # Unpack message
        job_id = params[0]
        previous_hash = binascii.a2b_hex(params[1])
        coinbase_1 = binascii.a2b_hex(params[2])
        coinbase_2 = binascii.a2b_hex(params[3])
        merkle_branch = [binascii.a2b_hex(h) for h in params[4]]
        version = binascii.a2b_hex(params[5])
        bits = binascii.a2b_hex(params[6])
        timestamp = params[7] # keep as ascii for calling mining.submit 
        clean_jobs = params[8]

        # Handle "clean_jobs"
        if clean_jobs:
            requeue = []
            try:
                _log.debug(f'🗑️ Emptying job queue...')
                while True:
                    item = recv_queue.get_nowait()
                    if item[0] != 'job':
                        requeue.append(item)
            except asyncio.QueueEmpty:
                _log.debug(f'🗑️ Job queue emptied.')
                
                # Re-queue non-"job" items removed from `recv_queue`
                for item in requeue:
                    await recv_queue.put(item)
    
                # Interrupt current job
                if interrupt_work:
                    _log.debug(f'🪓 Interrupting execution...')
                    shapool_.interrupt_execution()

        # Generate extranonce2
        extra_nonce_2 = StratumClient._generate_extra_nonce(self._extra_nonce_2_size)

        # Generate coinbase_hash
        coinbase_bin = StratumClient._generate_coinbase_hash(coinbase_1, self._extra_nonce_1, extra_nonce_2, coinbase_2) 

        # Generate merkle_root
        merkle_root = StratumClient._generate_merkle_root(merkle_branch, coinbase_bin)

        # Generate first_block, second_block
        first_block, second_block = shapool.Shapool._pack_job(\
            version, previous_hash, merkle_root, binascii.a2b_hex(timestamp), bits)

        # Generate midstate
        midstate_ = shapool.Shapool._precompute_midstate(first_block)

        # Push job
        extra_nonce_2 = binascii.b2a_hex(extra_nonce_2).decode('utf-8')
        job = ('job', (job_id, extra_nonce_2, timestamp, midstate_, second_block,),)
        await recv_queue.put(job)

    @staticmethod
    def _generate_merkle_root(merkle_branch, coinbase_hash):
        merkle_root = coinbase_hash

        for h in merkle_branch:
            merkle_root += h 
            merkle_root = hashlib.sha256(hashlib.sha256(merkle_root).digest()).digest()

        return merkle_root[::-1]

    @staticmethod
    def _generate_coinbase_hash(coinbase_1, extra_nonce_1, extra_nonce_2, coinbase_2):
        coinbase_bin = coinbase_1 + extra_nonce_1 + extra_nonce_2 + coinbase_2
        return hashlib.sha256(hashlib.sha256(coinbase_bin).digest()).digest()

    @staticmethod
    def _generate_extra_nonce(size):
        return os.urandom(size)
