import argparse
import asyncio
from datetime import datetime, timezone
import getpass
from icepool import icepool
import logging
import os
import queue
import sys
import time
import toml

from . import shapool
from . import stratum

_log = logging.getLogger('shapool-client.main')

def _heartbeat_forever():
    while True:
        _log.info(f'🕙 {datetime.now(timezone.utc).astimezone()}')
        time.sleep(5*60)

async def _run_shapool_forever(shapool_, worker_name, recv_queue, send_queue, timeout_s):
    while True:
        _log.info(f'🪑 [{worker_name}] Waiting for work...')

        method, params, = await recv_queue.get()

        if method == 'job':
            job_id, extra_nonce_2, timestamp, midstate_, second_block = params

            _log.info(f'⛏  [{worker_name}] Starting new job ({job_id=})...')

            shapool_.update_job(midstate_, second_block)
            shapool_.start_execution()  # start executing...

            loop = asyncio.get_running_loop()
            ready = await loop.run_in_executor(None, shapool_.poll_until_ready_or_timeout, timeout_s)

            if ready:
                nonce = shapool_.get_result()
                # TODO verify nonce meets difficulty
                if nonce:
                    _log.info(f'🍾 [{worker_name}] Success! ({job_id=})')
                    await send_queue.put(
                        ('mining.submit', [worker_name, job_id, extra_nonce_2, timestamp, nonce],))
                else:
                    _log.warning(f'🤷‍ [{worker_name}] READY without result...')
            else:
                _log.info(f'🛑 [{worker_name}] Timed out...')

            shapool_.reset()

        elif method == 'set_difficulty':
            difficulty, = params
            _log.info(f'🤹‍ [{worker_name}] Would set difficulty, but not implemented... {difficulty=}')
            # TODO implement setting difficulty
            # Base difficulty = 1 = 32 zeroes
            #                   2 = 33 zeroes
            #                   4 = 34 zeroes
            #                   8 = 35 zeroes
            # ... zeroes = floor(log2(difficulty)) + 32
        else:
            _log.warning(f'🤷‍ [{worker_name}] Received unknown message type: {method=}({params=!r})')

async def _recv_forever(stratum_, shapool_, recv_queue, interrupt_work):
    while True:
        msg = await stratum_._recv()

        if 'result' in msg:
            id, result, error = msg["id"], msg["result"], msg["error"]
            _log.debug(f'📥 Call reponse received: {id=} ➡ {result=}')

            if error:
                stratum_._handle_error(error, msg)
            # TODO associate response with call?
        else:
            method = msg['method']
            params = msg['params']

            _log.debug(f'📥 Received call from server: {method=}')

            if method == 'mining.notify':
                await stratum_._handle_notify(params, recv_queue, shapool_, interrupt_work)
            elif method == 'mining.set_difficulty':
                await stratum_._handle_set_difficulty(params, recv_queue)
            else:
                _log.warning(\
                    f'🤷‍ Received unknown message type from server: {method=}')

async def _send_forever(stratum_, send_queue):
    while True:
        method, params = await send_queue.get()
        _log.debug(f'📤 Sending call to server: {method=} {params=}')
        await stratum_.call(method, params)

async def main(args, config):

    USER_AGENT = 'shapool-dev'

    # Unpack config
    worker_name = config['name']
    worker_password = config['password']
    host = config['host']
    port = config['port']
    number_of_devices = config['number_of_devices']
    cores_per_device = config['cores_per_device']
    timeout = config['timeout']
    interrupt_work = config['interrupt_work']

    # Initialize stratum client
    stratum_ = stratum.StratumClient(host, port)
    await stratum_.connect()
    await stratum_.subscribe(USER_AGENT)
    await stratum_.authorize(worker_name, worker_password)
    #await stratum_.suggest_difficulty(128)

    # Initialize icepool/shapool
    ctx = icepool.IcepoolContext()
    shapool_ = shapool.Shapool(ctx, number_of_devices, cores_per_device)
    shapool_.update_device_configs()

    recv_queue = asyncio.Queue()
    send_queue = asyncio.Queue()

    # Convert blocking function into async task
    loop = asyncio.get_running_loop()
    heartbeat_task = loop.run_in_executor(None, _heartbeat_forever)

    # Make rocket go now!
    await asyncio.gather(
        heartbeat_task,
        _recv_forever(stratum_, shapool_, recv_queue, interrupt_work),
        _send_forever(stratum_, send_queue),
        _run_shapool_forever(shapool_, worker_name, recv_queue, send_queue, timeout)
    )

if __name__ == '__main__':

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='A stratum (v1) mining client that interfaces with icepool. (https://github.com/jkiv/)')
    parser.add_argument('-v', '--verbose', default=0, help='Output more detailed logging info.', action='count')
    parser.add_argument('-c', '--config', default='~/.shapool/config.toml', help='Path to client configuration TOML file. default: ~/.shapool/config.toml')
    parser.add_argument('-n', '--name', help='Section name in config file to use for worker. default: (first)')
    parser.add_argument('-p', '--password', default=False, help='Prompt for password, if not supplied in configuration. default: False', action='store_true')
    args = parser.parse_args()

    # Load configuration file
    args.config = os.path.abspath(os.path.expanduser(args.config))
    config = toml.load(args.config)

    # Use particular name from config, if supplied
    if args.name:
        config_name = args.name
    else:
        config_name = next(iter(config))

    worker_config = config[config_name]

    # Handle --verbose
    if args.verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose == 1:
        logging.basicConfig(level=logging.INFO)

    # Handle password options, if required 
    if args.password:
        worker_config['password'] = getpass.getpass()
    elif 'password-env' in worker_config:
        worker_config['password'] = os.getenv([worker_config['password-env']], '')
    elif 'password' not in worker_config:
        worker_config['password'] = ''

    # Handle other option defaults
    if 'timeout' not in worker_config:
        worker_config['timeout'] = 5*60
    
    if 'interrupt_work' not in worker_config:
        worker_config['interrupt_work'] = True

    # TODO proper validation of config (schema)

    _log.info(f'Using worker configuration \'{config_name}\' from \'{args.config}\'...')

    asyncio.run(main(args, worker_config), debug=(args.verbose == 2))