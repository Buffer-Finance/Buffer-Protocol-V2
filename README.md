# Buffer-Protocol-V2


## Set Up for running the testcases (Linux)


## Install

### Brownie
```bash
pip install eth-brownie
```
### OpenZeppelin
```bash
brownie pm install OpenZeppelin/openzeppelin-contracts@4.3.2
```

## Tasks

### Create and activate a virtual environment

```bash
python3 -m venv env
```
```bash
source env/bin/activate
```
### Update brownie.yaml

#### In the brownie.yaml fiile, under compiler, update the remapping for OpenZeppelin

```bash
remappings: 
      - '@openzeppelin=$HOME/.brownie/packages/OpenZeppelin/openzeppelin-contracts@4.3.2'
```

### Add an environment file (.env) to the folder

```bash
touch .env
```

### Run tests

```bash
brownie test
```
