from blockchain import BlockChain, Block
from transaction import Transaction
from merkle_tree import MerkleTree
import random
import time
import copy
from flask import Flask, request
from multiprocessing import Process, Queue
import pickle
import requests
import sys
import getopt
import colorama

app = Flask(__name__)

# Parsing arguments when 
def parse_arguments(argv):
    inputfile = ''
    outputfile = ''
    color = ''
    list_of_miner_ip=[]
    try:
        opts, args = getopt.getopt(argv, "hp:i:c:m:", ["port=", "ifile=","color=","mode="])
    except getopt.GetoptError:
        print ('test.py -p<port> -i <inputfile of list of IPs of other miners> -c <color w|r|h|y|m|c> -m <mode 1/2>')
        sys.exit(2)
    for opt, arg in opts:
        mode = 1
        if opt == '-h':
            print ('test.py -p<port> -i <inputfile of list of IPs of other miners> -c <color w|r|h|y|m|c> -m <mode 1/2>')
            sys.exit()
        elif opt in ("-p", "--port"):
            my_port = arg
        elif opt in ("-i", "--ifile"):
            inputfile = arg
            f = open(inputfile, "r")
            for line in f:
                list_of_miner_ip.append(line)
            print(list_of_miner_ip)
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
        elif opt in ("-m", "--mode"):
            mode_arg = arg
            if mode_arg == "2":
                mode = 2
            else:
                mode = 1
    return my_port, list_of_miner_ip, color, mode

MY_PORT, LIST_OF_MINER_IP, COLOR, MODE = parse_arguments(sys.argv[1:])
# MY_IP will be a single string in the form of "127.0.0.1:5000"
# LIST_OF_MINER_IP will be a list of strings in the form of ["127.0.0.1:5000","127.0.0.1:5001","127.0.0.1:5002"]


class Miner:
    def __init__(self, blockchain):
        self.blockchain = copy.deepcopy(blockchain)
        self.nonce = 0
        self.current_time = str(time.time())

    def mine(self, merkletree):
        block = Block(merkletree, self.blockchain.last_hash,
                      merkletree.get_root(), self.current_time, self.nonce)
        if self.blockchain.add(block):
            # If the add is successful, reset
            self.reset_new_mine()
            # print(MY_IP)
            return True
        self.nonce += 1
        # print(block.header_hash())
        return False

    def reset_new_mine(self):
        self.nonce = 0
        self.current_time = str(time.time())
        self.blockchain.resolve()
        # need to include proper checks when new block is added
        # check should be in here or resolve?
        # self.blockchain.difficulty_adjust()

    def network_block(self, block):
        if self.blockchain.network_add(block):
            self.reset_new_mine()


# Random Merkletree
def create_sample_merkle():
    merkletree = MerkleTree()
    for i in range(100):
        merkletree.add(random.randint(100, 1000))
    merkletree.build()
    return merkletree


def create_merkle(transaction_queue):
    list_of_raw_transactions = []
    list_of_validated_transactions = []
    while not transaction_queue.empty():
        list_of_raw_transactions.append(
            Transaction.from_json(transaction_queue.get()))
    for transaction in list_of_raw_transactions:
        # TODO: check if transaction is okay
        if True:
            list_of_validated_transactions.append(transaction)

    merkletree = MerkleTree()
    # TODO: Add coinbase TX
    # merkletree.add(COINBASE_TRANSACTION)
    for transaction in list_of_validated_transactions:
        merkletree.add(transaction.to_json())
    merkletree.build()
    return merkletree


def start_mining(block_queue, transaction_queue):
    merkletree = create_sample_merkle()
    blockchain = BlockChain()
    miner = Miner(blockchain)
    miner_status = False
    while True:
        while True:
            miner_status = miner.mine(merkletree)
            if miner_status:
                sending_block = blockchain.last_block()
                data = pickle.dumps(sending_block, protocol=2)
                for miner_ip in LIST_OF_MINER_IP:
                    send_failed = True
                    while send_failed:
                        try:
                            requests.post("http://"+miner_ip+"/block", data=data)
                            send_failed = False
                        except:
                            time.sleep(0.1)
                break
            # Checks value of nonce, as checking queue every cycle makes it very laggy
            if miner.nonce % 10000 == 0:
                if not block_queue.empty():
                    new_block = block_queue.get()
                    miner.network_block(new_block)
                    break
        # Section run if the miner found a block or receives a block that has been broadcasted
        print(COLOR + (str(miner.blockchain) if MODE==1 else str(miner.blockchain).split("~~~")[1]))
        # merkletree = create_merkle(transaction_queue)

block_queue = Queue()
transaction_queue = Queue()

@app.route('/block', methods=['POST'])
def new_block_network():
    new_block = pickle.loads(request.get_data())
    block_queue.put(new_block)
    return ""


@app.route('/transaction')
def new_transaction_network():
    # Needs to add a proper transaction object, currently thing will fail
    transaction_queue.put("a")


if __name__ == '__main__':
    p = Process(target=start_mining, args=(block_queue, transaction_queue,))
    p.start()
    app.run(debug=True, use_reloader=False, port=MY_PORT)
    p.join()
