# shapool-client

`shapool-client` is a [stratum v1](https://en.bitcoin.it/wiki/Stratum_mining_protocol) mining client that interfaces with an [`icepool`](https://github.com/jkiv/icepool-board) cluster running [`shapool-core`](https://github.com/jkiv/shapool-core).

```
$ python3 -m shapool --help
python3 -m shapool --help
usage: __main__.py [-h] [-v] [-c CONFIG] [-n NAME] [-p]

A stratum (v1) mining client that interfaces with icepool. (https://github.com/jkiv/)

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Output more detailed logging info.
  -c CONFIG, --config CONFIG
                        Path to client configuration TOML file. default: ~/.shapool/config.toml
  -n NAME, --name NAME  Section name in config file to use for worker. default: (first)
  -p, --password        Prompt for password, if not supplied in configuration. default: False
```

### Installation

#### ... via PyPI

```bash
# TODO pip install shapool
```

#### ... from source:

Building requires `make` and `gcc`.

```
$ make dist
$ pip install dist/shapool.*.tar.gz 
```

### Configuration

`shapool` uses a [TOML](https://github.com/toml-lang/toml) file for configuration.

The default location is `~/.shapool/config.toml`. A different configuration can be provided at run-time using the command-line argument `-c` or `--config`.

```toml
[shapool-example1]
name='jkiv.shapool-example1'
host="stratum.example.com"
port=3333
number_of_devices=3
cores_per_device=2

[shapool-example2]
name='jkiv.shapool-example2'
host="stratum.example.com"
port=3333
number_of_devices=1
cores_per_device=1
```

Each TOML section describes a worker configuration. By default, the first section in the file is used. In the example above, this would be `shapool-example1`.

A different section can be used at run-time using the command-line argument `-n` or `--name`. The section `shapool-example2` can be used instead:

```
$ python3 -m shapool --name shapool-example2
```

### Donate

Please consider supporting this project and others like it by donating:

* ☕: [ko-fi.com/jkiv_](https://ko-fi.com/jkiv_)
* ₿: `13zRrs1YDdooUN5WtfXRSDn8KnJdok4qG9`
