import time
import copy
import binascii

from ecdsa import SigningKey
from transaction import Transaction
from blockchain import BlockChain, Block, Ledger
from merkle_tree import MerkleTree, verify_proof


class Miner:

    def __init__(self, blockchain, public_key=None):
        self.blockchain = copy.deepcopy(blockchain)
        self.nonce = 0
        self.current_time = str(time.time())
        self.public_key = public_key
        self.public_key_str = binascii.hexlify(public_key.to_string()).decode()

    # Mine next block with latest block in longest chain as prev_hash
    def mine(self, merkletree, ledger):
        block = Block(merkletree, self.blockchain.last_hash,
                      merkletree.get_root(), self.current_time, self.nonce, ledger)

        if self.blockchain.add(block):
            # If the add is successful, reset
            self.reset_new_mine()
            return True
        # Increase nonce everytime the mine fails
        self.nonce += 1
        return False

    # Mine from a block that was validated in the past
    def mine_from_old_block(self, merkletree, ledger, block_hash):
        block = Block(merkletree, block_hash, merkletree.get_root(),
                      self.current_time, self.nonce, ledger)

        if self.blockchain.add(block):
            # If the add is successful, reset
            self.reset_new_mine()
            return True
        # Increase nonce everytime the mine fails
        self.nonce += 1
        return False

    # Prepare to mine the next block by resetting
    # nonce, time and getting most updated blockchain
    def reset_new_mine(self):
        self.nonce = 0
        self.current_time = str(time.time())
        self.blockchain.resolve()

    # Called when a new block is received by another miner
    def network_block(self, block):
        if self.blockchain.network_add(block):
            self.reset_new_mine()
            return True
        else:
            return False

    # Create merkle tree based on transactions received
    # ignore transactions that were made in double_spending
    def create_merkle(self, transaction_queue, tx_to_ignore=None):
        block = self.blockchain.last_block()
        if block is None:
            # genesis block, create a ledger
            ledger = Ledger()
        else:
            # work on latest ledger
            ledger = block.ledger
            
        list_of_raw_transactions = []
        list_of_validated_transactions = []

        # get transactions from queue
        while not transaction_queue.empty():
            list_of_raw_transactions.append(
                transaction_queue.get())

        # verify transactions
        for transaction in list_of_raw_transactions:
            if tx_to_ignore is not None and transaction in tx_to_ignore:
                print(f"Ignoring transaction: {transaction}")
            elif ledger.verify_transaction(transaction, list_of_validated_transactions, binascii.hexlify(block.header_hash()).decode(), self.blockchain):
                # only verified transactions get included in merkletree
                list_of_validated_transactions.append(transaction)
                print("Verification complete.")
        
        merkletree = MerkleTree()
        # coinbase transaction is the first tx in the merkle tree
        coinbase_sender_pk = SigningKey.generate()
        coinbase_sender_vk = coinbase_sender_pk.get_verifying_key()
        merkletree.add(Transaction(coinbase_sender_vk, self.public_key,
                                   100, sender_pk=coinbase_sender_pk).to_json())
        ledger.coinbase_transaction(self.public_key_str)

        # add other transactions to merkle tree
        for transaction in list_of_validated_transactions:
            transaction_object = transaction.to_json()
            merkletree.add(transaction_object)
        merkletree.build()
        return merkletree, ledger