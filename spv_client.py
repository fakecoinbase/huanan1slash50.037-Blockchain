import sys
import copy
import time
import json
import ecdsa
import getopt
import pickle
import random
import requests
import binascii

from ecdsa import SigningKey
from transaction import Transaction
from merkle_tree import verify_proof
from merkle_tree import verify_proof
from flask import Flask, request, jsonify
from spv_blockchain import SPVBlock, SPVBlockChain


app = Flask(__name__)


# Parsing arguments when entered via CLI
def parse_arguments(argv):
    inputfile = ''
    list_of_miner_ip = []
    private_key = None
    try:
        opts, args = getopt.getopt(
            argv, "hp:m:w:", ["port=", "iminerfile=", "wallet="])
    # Only port and input is mandatory
    except getopt.GetoptError:
        print('SPVClient.py -p <port> -m <inputfile of list of IPs of other miners> -w <hashed public key of SPVClient>')
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print('SPVClient.py -p <port> -m <inputfile of list of IPs of other miners> -w <hashed public key of SPVClient>')
            sys.exit()

        elif opt in ("-p", "--port"):
            my_port = arg

        elif opt in ("-m", "--iminerfile"):
            inputfile = arg
            f = open(inputfile, "r")
            for line in f:
                list_of_miner_ip.append(line)

        elif opt in ("-w", "--wallet"):
            if arg != "NO_WALLET":
                private_key = arg

    return my_port, list_of_miner_ip, private_key

# Get data from arguments
MY_PORT, LIST_OF_MINER_IP, PRIVATE_KEY = parse_arguments(sys.argv[1:])
# MY_PORT will be a single string in the form of "5000"
# LIST_OF_MINER_IP will be a list of strings in the form of ["127.0.0.1:5000","127.0.0.1:5001","127.0.0.1:5002"]
# PRIVATE_KEY is a SigningKey in String format

# Converts PRIVATE_KEY from String to Signing key, and generates PUBLIC_KEY
if PRIVATE_KEY is None:
    PRIVATE_KEY = ecdsa.SigningKey.generate()
else:
    PRIVATE_KEY = ecdsa.SigningKey.from_string(
        binascii.unhexlify(bytes(PRIVATE_KEY, 'utf-8')))
PUBLIC_KEY = PRIVATE_KEY.get_verifying_key()
PUBLIC_KEY_STRING = binascii.hexlify(PUBLIC_KEY.to_string()).decode()
print("Public key: " + PUBLIC_KEY_STRING)


class SPVClient:
    '''
    Each SPVClient acts as a wallet, and should have a private and public key.
    The SPVClient should be able to store all the headers of the blockchain. 
    The SPVClient should also be able to send transactions, receive and verify them.
    '''

    def __init__(self, private_key, public_key, public_key_string, spv_blockchain):
        # Public key of the wallet to check privte key for verification.
        self.PUBLIC_KEY = public_key
        self.PUBLIC_KEY_STRING = public_key_string
        # Private key of the wallet to sign outgoing transactions.
        self.PRIVATE_KEY = private_key
        self.spv_blockchain = spv_blockchain


spv_blockchain = SPVBlockChain()
spv_client = SPVClient(PRIVATE_KEY, PUBLIC_KEY,
                       PUBLIC_KEY_STRING, spv_blockchain)


# Returns an ordered list of header hashes of the longest chain from genesis block
@app.route('/request_blockchain_header_hash')
def request_blockchain_headers():
    spv_client.spv_blockchain.resolve()
    return jsonify({"blockchain_headers_hash": spv_client.spv_blockchain.cleaned_keys})


# Returns an ordered list of blocks of the longest chain from genesis block
# For SPVClient, the list of ordered transactions for every block is not included
@app.route('/request_blockchain')
def request_blockchain():
    spv_client.spv_blockchain.resolve()
    cleaned_keys, chain = spv_client.spv_blockchain.cleaned_keys, spv_client.spv_blockchain.chain
    lst_chain = []
    for i in cleaned_keys:
        block_dictionary = dict()
        block = chain[i]
        block_dictionary["header_hash"] = i
        block_dictionary["previous_header_hash"] = block.previous_header_hash
        block_dictionary["hash_tree_root"] = binascii.hexlify(
            block.hash_tree_root).decode()
        block_dictionary["timestamp"] = block.timestamp
        block_dictionary["nonce"] = block.nonce
        lst_chain.append(block_dictionary)
    return jsonify(lst_chain)


# Returns an unordered list of all blocks within client
# For SPVClient, the list of ordered transactions for every block is not included
@app.route('/request_full_blockchain')
def request_full_blockchain():
    chain = spv_client.spv_blockchain.chain
    dic_chain = dict()
    for i in chain:
        block_dictionary = dict()
        block = chain[i]
        block_dictionary["header_hash"] = i
        block_dictionary["previous_header_hash"] = block.previous_header_hash
        block_dictionary["hash_tree_root"] = binascii.hexlify(
            block.hash_tree_root).decode()
        block_dictionary["timestamp"] = block.timestamp
        block_dictionary["nonce"] = block.nonce
        dic_chain[block_dictionary["header_hash"]] = block_dictionary
    return jsonify(dic_chain)


# Returns full information for that particular block, identified by its header hash
# For SPVClient, the list of ordered transactions in the block is not included
@app.route('/request_block/<header_hash>')
def request_block(header_hash):
    chain = spv_client.spv_blockchain.chain
    try:
        block = chain[header_hash]
    except:
        return jsonify("Unable to find block.")
    block_dictionary = dict()
    block_dictionary["header_hash"] = header_hash
    block_dictionary["previous_header_hash"] = block.previous_header_hash
    block_dictionary["hash_tree_root"] = binascii.hexlify(
        block.hash_tree_root).decode()
    block_dictionary["timestamp"] = block.timestamp
    block_dictionary["nonce"] = block.nonce
    return jsonify(block_dictionary)


# Returns amount of coins in the queried SPVClient or Miner's wallet
# SPVClient will will retrieve information from a random full node/ Miner
@app.route('/account_balance')
def request_my_account_balance():
    miner_ip = random.choice(LIST_OF_MINER_IP)
    try:
        response = json.loads(requests.get(
            "http://" + miner_ip + "/account_balance/" + PUBLIC_KEY_STRING).text)
        return jsonify(response)
    except:
        return jsonify("No coins in account yet.")


# Returns amount of coins of any existing wallet in the network
# Search based on the wallet's public key
@app.route('/account_balance/<public_key>')
def request_account_balance(public_key):
    miner_ip = random.choice(LIST_OF_MINER_IP)
    try:
        response = json.loads(requests.get(
            "http://" + miner_ip + "/account_balance/" + public_key).text)
        return jsonify(response)
    except:
        return jsonify("Cannot find account.")


# To broadcast to all miners when transaction is created
@app.route('/send_transaction', methods=['POST'])
def createTransaction():
    receiver_public_key = request.args.get('receiver', '')
    amount = request.args.get('amount', '')
    miner_ip = random.choice(LIST_OF_MINER_IP)
    try:
        response = json.loads(requests.get(
            "http://" + miner_ip + "/account_balance/" + spv_client.PUBLIC_KEY_STRING).text)
        balance = response["amount"]
    except:
        return jsonify("Cannot find account or no coins in account yet.")
    if balance >= int(amount):
        new_transaction = Transaction(
            spv_client.PUBLIC_KEY, receiver_public_key, int(amount), sender_pk=spv_client.PRIVATE_KEY)
    else:
        return jsonify("Insufficient balance in account to proceed.")

    for miner in LIST_OF_MINER_IP:
        not_sent = True
        # Execute POST request to broadcast transaction
        while not_sent:
            try:
                requests.post(
                    url="http://" + miner + "/transaction",
                    data=new_transaction.to_json()
                )
                not_sent = False
            except:
                time.sleep(0.1)
    return jsonify(new_transaction.to_json())


# Returns information about the particular transactions, including number of confirmations
# SPVClient will ask a random full node/ Miner for merkle tree's proof and verify locally with
# the merkle tree root and header hashes
@app.route('/verify_transaction/<txid>', methods=['GET'])
def verify_Transaction(txid):
    miner_ip = random.choice(LIST_OF_MINER_IP)
    try:
        response = json.loads(requests.post(
            "http://" + miner_ip + "/verify_transaction_from_spv", data=txid).text)
    except:
        return jsonify("TXID not found.")
    entry = response["entry"]
    proof_string = response["proof"]
    proof_bytes = []
    for i in proof_string:
        if i == "None":
            proof_bytes.append(None)
        else:
            proof_bytes.append(
                [i[0], binascii.unhexlify(bytes(i[1], 'utf-8'))])
    root_bytes = binascii.unhexlify(bytes(response["root"], 'utf-8'))
    verify = verify_proof(entry, proof_bytes, root_bytes)
    entry_dictionary = json.loads(entry)
    if verify:
        if entry_dictionary["txid"] != txid:
            return jsonify("Received transaction ID does not match sent TXID.")

        spv_client.spv_blockchain.resolve()
        for count, i in enumerate(spv_client.spv_blockchain.cleaned_keys):
            # Finds corresponding block header
            if spv_client.spv_blockchain.chain[i].hash_tree_root == root_bytes:
                # Returns the position of block header in cleaned_keys
                reply = {"entry": entry, "proof": proof_string, "root": binascii.hexlify(root_bytes).decode(
                ), "verify": True, "confirmations": (len(spv_client.spv_blockchain.cleaned_keys) - count), "block_header": i}
                return jsonify(reply)
        return jsonify("No block headers found.")
    return jsonify("TXID not found.")


# Called by Miners, able to receive SPVBlock objects as Pickles from other Miners in body
@app.route('/block_header', methods=['POST'])
def new_block_header_network():
    new_block_header = pickle.loads(request.get_data())
    spv_client.spv_blockchain.network_add(new_block_header)
    return ""


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=MY_PORT)
