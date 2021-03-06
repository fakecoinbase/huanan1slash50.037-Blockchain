import sys
import time
import copy
import json
import ecdsa
import random
import pickle
import getopt
import logging
import requests
import colorama
import binascii

from miner import Miner
from ecdsa import SigningKey
from transaction import Transaction
from spv_blockchain import SPVBlock
from flask import Flask, request, jsonify
from multiprocessing import Process, Queue
from blockchain import BlockChain, Block, Ledger
from merkle_tree import MerkleTree, verify_proof


app = Flask(__name__)

# This section is to get rid of Flask logging messages
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)


# Parsing arguments when entered via CLI
def parse_arguments(argv):
    inputfile = ''
    outputfile = ''
    color = ''
    selfish = False
    list_of_miner_ip = []
    list_of_spv_ip = []
    mode = 1
    private_key = None
    try:
        opts, args = getopt.getopt(
            argv, "hp:m:s:c:d:f:w:", ["port=", "iminerfile=", "ispvfile=", "color=", "description=", "selfish=", "wallet="])
    # Only port and input is mandatory
    except getopt.GetoptError:
        print('miner.py -p <port> -m <inputfile of list of IPs of other miners> -s <inputfile of list of IPs of SPV clients> -c <color w|r|h|y|m|c> -d <description 1/2> -s <1 if selfish miner>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('miner.py -p <port> -m <inputfile of list of IPs of other miners> -s <inputfile of list of IPs of SPV clients> -c <color w|r|h|y|m|c> -d <description 1/2> -s <1 if selfish miner>')
            sys.exit()
        elif opt in ("-p", "--port"):
            my_port = arg
        elif opt in ("-m", "--iminerfile"):
            inputfile = arg
            f = open(inputfile, "r")
            for line in f:
                list_of_miner_ip.append(line.strip())
        elif opt in ("-s", "--ispvfile"):
            inputfile = arg
            f = open(inputfile, "r")
            for line in f:
                list_of_spv_ip.append(line.strip())
        elif opt in ("-c", "--color"):
            color_arg = arg
            if color_arg == "w":
                color = colorama.Fore.WHITE
            elif color_arg == "r":
                color = colorama.Fore.RED
            elif color_arg == "g":
                color = colorama.Fore.GREEN
            elif color_arg == "y":
                color = colorama.Fore.YELLOW
            elif color_arg == "b":
                color = colorama.Fore.BLUE
            elif color_arg == "m":
                color = colorama.Fore.MAGENTA
            elif color_arg == "c":
                color = colorama.Fore.CYAN
        elif opt in ("-d", "--description"):
            mode_arg = arg
            if mode_arg == "2":
                mode = 2
        elif opt in ("-f", "--selfish"):
            if arg == "1":
                selfish = True
        elif opt in ("-w", "--wallet"):
            if arg != "NO_WALLET":
                private_key = arg
    return my_port, list_of_miner_ip, list_of_spv_ip, color, mode, selfish, private_key


# Get data from arguments
MY_PORT, LIST_OF_MINER_IP, LIST_OF_SPV_IP, COLOR, MODE, SELFISH, PRIVATE_KEY = parse_arguments(
    sys.argv[1:])
# MY_PORT will be a single string in the form of "5000"
# LIST_OF_MINER_IP and LIST_OF_SPV_IP will be a list of strings in the form of ["127.0.0.1:5000","127.0.0.1:5001","127.0.0.1:5002"]
# COLOR is color of text using colorama library
# MODE is either 1 or 2, 1 is full details, 2 is shortform
# SELFISH if True, this miner will be a selfish miner
# PRIVATE_KEY is a SigningKey in String format


# Removes own IP from list
for count, i in enumerate(LIST_OF_MINER_IP):
    if i == ("127.0.0.1:" + MY_PORT):
        del LIST_OF_MINER_IP[count]

# Converts PRIVATE_KEY from String to Signing key, and generates PUBLIC_KEY
if PRIVATE_KEY is None:
    PRIVATE_KEY = ecdsa.SigningKey.generate()
else:
    PRIVATE_KEY = ecdsa.SigningKey.from_string(
        binascii.unhexlify(bytes(PRIVATE_KEY, 'utf-8')))
PUBLIC_KEY = PRIVATE_KEY.get_verifying_key()
PUBLIC_KEY_STRING = binascii.hexlify(PUBLIC_KEY.to_string()).decode()

# Starts the mining loop
def start_mining(block_queue, transaction_queue, blockchain_request_queue, blockchain_reply_queue):
    blockchain = BlockChain(LIST_OF_MINER_IP)
    miner = Miner(blockchain, PUBLIC_KEY)
    miner_status = False
    list_of_blocks_selfish = []
    SELFISH_LENGTH = 5
    list_of_collected_selfish_blocks = []
    selfish_flush = False
    # Infinite loop
    while True:
        # Create a merkel tree from transaction queue
        merkletree, ledger = miner.create_merkle(transaction_queue)

        while True:
            # Mines the nonce every round
            miner_status = miner.mine(merkletree, ledger)
            mine_or_recv = ""
            # Check if that mine is successful
            if miner_status:
                mine_or_recv = "Block MINED "
                sending_block = blockchain.last_block()
                mine_or_recv += binascii.hexlify(
                    sending_block.header_hash()).decode()

                # Grab the last block and send to network
                # If regular miner
                if not SELFISH:
                    data = pickle.dumps(sending_block, protocol=2)
                    for miner_ip in LIST_OF_MINER_IP:
                        send_failed = True
                        while send_failed:
                            try:
                                requests.post("http://"+miner_ip +
                                              "/block", data=data)
                                send_failed = False
                            except:
                                print("Send failed.", miner_ip)
                                time.sleep(0.2)
                    sending_spv_block = SPVBlock(sending_block)
                    data = pickle.dumps(sending_spv_block, protocol=2)
                    for spv_ip in LIST_OF_SPV_IP:
                        send_failed = True
                        while send_failed:
                            try:
                                requests.post("http://"+spv_ip +
                                              "/block_header", data=data)
                                send_failed = False
                            except:
                                print("Send failed.", spv_ip)
                                time.sleep(0.2)
                # If selfish miner
                elif SELFISH:
                    mine_or_recv += "\nSELFISH MINING\n"
                    list_of_blocks_selfish.append(sending_block)
                    # It will send only every n blocks
                    if len(list_of_blocks_selfish) >= SELFISH_LENGTH:
                        mine_or_recv += "SENDING SELFISH BLOCKS\n"
                        selfish_flush = True
                        for block in list_of_blocks_selfish:
                            block_data = pickle.dumps(block, protocol=2)
                            for miner_ip in LIST_OF_MINER_IP:
                                send_failed = True
                                while send_failed:
                                    try:
                                        requests.post("http://"+miner_ip +
                                                      "/block", data=block_data)
                                        send_failed = False
                                    except:
                                        time.sleep(0.1)
                        list_of_blocks_selfish = []
                break
            # Runs this area only once every 100 nonce, as checking queue every cycle makes it very laggy
            if miner.nonce % 100 == 0:
                # Check if new blocks have been detected
                block_queue_status_initial = block_queue.empty()
                while not block_queue.empty():
                    mine_or_recv += "Block RECEIVED "
                    new_block = block_queue.get()
                    if not SELFISH:
                        miner.network_block(new_block)
                    elif SELFISH:
                        list_of_collected_selfish_blocks.append(new_block)
                        if len(list_of_collected_selfish_blocks) > SELFISH_LENGTH or selfish_flush:
                            for i in list_of_collected_selfish_blocks:
                                miner.network_block(i)
                            for block in list_of_blocks_selfish:
                                block_data = pickle.dumps(block, protocol=2)
                                for miner_ip in LIST_OF_MINER_IP:
                                    send_failed = True
                                    while send_failed:
                                        try:
                                            requests.post("http://"+miner_ip +
                                                          "/block", data=block_data)
                                            send_failed = False
                                        except:
                                            time.sleep(0.1)
                            miner.blockchain.resolve()
                            list_of_collected_selfish_blocks = []
                            list_of_blocks_selfish = []
                            selfish_flush = False
                    mine_or_recv += binascii.hexlify(
                        new_block.header_hash()).decode() + " "
                if not block_queue_status_initial:
                    mine_or_recv += "\n"
                    break
                # Checks if any of the endpoints requested a copy of the blockchain
                if not blockchain_request_queue.empty():
                    blockchain_request_queue.get()
                    blockchain_reply_queue.put((copy.deepcopy(blockchain.cleaned_keys), copy.deepcopy(blockchain.chain),
                                                copy.deepcopy(blockchain.retrieve_ledger())))
        # Section runs if the miner found a block or receives a block that has been broadcasted
        print(COLOR + "Public key: {}\n".format(PUBLIC_KEY_STRING) + "PORT: {}\n".format(MY_PORT) + mine_or_recv + "\n" +
              (str(miner.blockchain) if MODE == 1 else str(miner.blockchain).split("~~~\n")[1]))


# Queue objects for passing stuff between Flask and mining process
block_queue = Queue()
transaction_queue = Queue()
blockchain_request_queue = Queue()
blockchain_reply_queue = Queue()

# Returns an ordered list of header hashes of the longest chain from genesis block
@app.route('/request_blockchain_header_hash')
def request_blockchain_headers():
    blockchain_request_queue.put(None)
    return jsonify({"blockchain_headers_hash": blockchain_reply_queue.get()[0]})

# Returns an ordered list of blocks of the longest chain from genesis block
@app.route('/request_blockchain')
def request_blockchain():
    blockchain_request_queue.put(None)
    queue_reply = blockchain_reply_queue.get()
    cleaned_keys, chain = queue_reply[0], queue_reply[1]
    lst_chain = []
    for i in cleaned_keys:
        block_dictionary = dict()
        block = chain[i]
        block_dictionary["header_hash"] = binascii.hexlify(
            block.header_hash()).decode()
        block_dictionary["previous_header_hash"] = block.previous_header_hash
        block_dictionary["hash_tree_root"] = binascii.hexlify(
            block.hash_tree_root).decode()
        block_dictionary["timestamp"] = block.timestamp
        block_dictionary["nonce"] = block.nonce
        transaction_list = []
        for i in block.transactions.leaf_set:
            transaction_list.append(i.decode())
        block_dictionary["transactions"] = transaction_list
        lst_chain.append(block_dictionary)
    return jsonify(lst_chain)

# Returns an unordered list of all blocks within client
@app.route('/request_full_blockchain')
def request_full_blockchain():
    blockchain_request_queue.put(None)
    chain = blockchain_reply_queue.get()[1]
    dic_chain = dict()
    for i in chain:
        block_dictionary = dict()
        block = chain[i]
        block_dictionary["header_hash"] = binascii.hexlify(
            block.header_hash()).decode()
        block_dictionary["previous_header_hash"] = block.previous_header_hash
        block_dictionary["hash_tree_root"] = binascii.hexlify(
            block.hash_tree_root).decode()
        block_dictionary["timestamp"] = block.timestamp
        block_dictionary["nonce"] = block.nonce
        transaction_list = []
        for i in block.transactions.leaf_set:
            transaction_list.append(i.decode())
        block_dictionary["transactions"] = transaction_list
        dic_chain[block_dictionary["header_hash"]] = block_dictionary
    return jsonify(dic_chain)

# Returns full information for that particular block, identified by its header hash
@app.route('/request_block/<header_hash>')
def request_block(header_hash):
    blockchain_request_queue.put(None)
    chain = blockchain_reply_queue.get()[1]
    try:
        block = chain[header_hash]
    except:
        return jsonify("Unable to find block")
    block_dictionary = dict()
    block_dictionary["header_hash"] = header_hash
    block_dictionary["previous_header_hash"] = block.previous_header_hash
    block_dictionary["hash_tree_root"] = binascii.hexlify(
        block.hash_tree_root).decode()
    block_dictionary["timestamp"] = block.timestamp
    block_dictionary["nonce"] = block.nonce
    transaction_list = []
    for i in block.transactions.leaf_unset:
        transaction_list.append(i.decode())
    block_dictionary["transactions"] = transaction_list
    return jsonify(block_dictionary)

# Returns amount of coins in the queried SPVClient or Miner's wallet
@app.route('/account_balance')
def request_my_account_balance():
    blockchain_request_queue.put(None)
    ledger = blockchain_reply_queue.get()[2]
    try:
        reply = {"public_key": PUBLIC_KEY_STRING,
                 "amount": ledger[PUBLIC_KEY_STRING]}
        return jsonify(reply)
    except:
        return jsonify("No coins in account yet")

# Returns amount of coins of any existing wallet in the network
# Search based on the wallet's public key
@app.route('/account_balance/<public_key>')
def request_account_balance(public_key):
    blockchain_request_queue.put(None)
    ledger = blockchain_reply_queue.get()[2]
    print(ledger)
    try:
        reply = {"public_key": public_key, "amount": ledger[public_key]}
        return jsonify(reply)
    except:
        return jsonify("Cannot find account or no coins in account yet")

# To broadcast to all miners when transaction is created
@app.route('/send_transaction', methods=['POST'])
def request_send_transaction():
    receiver_public_key = request.args.get('receiver', '')
    amount = request.args.get('amount', '')
    blockchain_request_queue.put(None)
    ledger = blockchain_reply_queue.get()[2]
    balance = ledger[PUBLIC_KEY_STRING]
    if balance >= int(amount):
        new_transaction = Transaction(
            PUBLIC_KEY, receiver_public_key, int(amount), sender_pk=PRIVATE_KEY)
    else:
        return ("Insufficient balance in account to proceed.")

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
    not_sent = True
    return jsonify(new_transaction.to_json())

# Returns information about the particular transactions, including number of confirmations
@app.route('/verify_transaction/<txid>', methods=['GET'])
def verify_Transaction(txid):
    blockchain_request_queue.put(None)
    blockchain_tuple = blockchain_reply_queue.get()
    cleaned_keys, chain = blockchain_tuple[0], blockchain_tuple[1]
    for count, i in enumerate(cleaned_keys):
        merkle_tree = chain[i].transactions
        for j in merkle_tree.leaf_set:
            if json.loads(j.decode())["txid"] == txid:
                proof_bytes = merkle_tree.get_proof(j.decode())
                proof_string = []
                for k in proof_bytes:
                    if k is None:
                        proof_string.append("None")
                    else:
                        proof_string.append(
                            [k[0], binascii.hexlify(k[1]).decode()])
                root_bytes = merkle_tree.get_root()
                root_string = binascii.hexlify(root_bytes).decode()
                reply = {"entry": j.decode(), "proof": proof_string, "root": root_string, "verify": verify_proof(
                    j.decode(), proof_bytes, root_bytes), "confirmations": (len(cleaned_keys) - count), "block_header": i}
                return jsonify(reply)
    return jsonify("No TXID found.")

# Called by SPV to get the merkle tree proof data from Miner
@app.route('/verify_transaction_from_spv', methods=['POST'])
def verify_transaction_from_spv():
    data = request.data.decode()
    blockchain_request_queue.put(None)
    blockchain_tuple = blockchain_reply_queue.get()
    cleaned_keys, chain = blockchain_tuple[0], blockchain_tuple[1]
    for count, i in enumerate(cleaned_keys):
        merkle_tree = chain[i].transactions
        for j in merkle_tree.leaf_set:
            if json.loads(j.decode())["txid"] == data:
                proof_bytes = merkle_tree.get_proof(j.decode())
                proof_string = []
                for k in proof_bytes:
                    if k is None:
                        proof_string.append("None")
                    else:
                        proof_string.append(
                            [k[0], binascii.hexlify(k[1]).decode()])
                root_bytes = merkle_tree.get_root()
                root_string = binascii.hexlify(root_bytes).decode()
                reply = {"entry": j.decode(), "proof": proof_string,
                         "root": root_string}
                return jsonify(reply)
    return ""

# Called by other Miners, able to receive Block objects as Pickles from other Miners in body
@app.route('/block', methods=['POST'])
def new_block_network():
    new_block = pickle.loads(request.get_data())
    block_queue.put(new_block)
    return ""

# Called by other Miners and SPV, able to receive Transactions as json in body
@app.route('/transaction', methods=['POST'])
def new_transaction_network():
    new_transaction = Transaction.from_json(request.data.decode())
    transaction_queue.put(new_transaction)
    return ""


if __name__ == '__main__':
    p = Process(target=start_mining, args=(block_queue, transaction_queue,
                                           blockchain_request_queue, blockchain_reply_queue,))
    p.start()
    app.run(debug=True, use_reloader=False, port=MY_PORT)
    p.join()
