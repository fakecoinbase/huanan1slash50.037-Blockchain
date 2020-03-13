from merkle_tree import MerkleTree
import hashlib
import random
import time
import binascii
import copy


class Block:
    def __init__(self, transactions, previous_header_hash, hash_tree_root, timestamp, nonce):
        # Instantiates object from passed values
        self.transactions = transactions  # MerkleTree object
        self.previous_header_hash = previous_header_hash  # Previous hash in string
        self.hash_tree_root = hash_tree_root  # tree root in bytes
        self.timestamp = timestamp  # unix time in string
        self.nonce = nonce  # nonce in int

    def header_hash(self):
        # Creates header value
        header_joined = binascii.hexlify(
            self.hash_tree_root).decode() + str(self.timestamp) + str(self.nonce)
        if self.previous_header_hash is not None:
            header_joined = self.previous_header_hash + header_joined
        # Double hashes the header value, coz bitcoin does the same
        m = hashlib.sha256()
        m.update(header_joined.encode())
        round1 = m.digest()
        m = hashlib.sha256()
        m.update(round1)
        return m.digest()

class SPVBlock:
    def __init__(self, block):
        # Instantiates object from passed values
        self.header_hash = block.header_hash()
        self.prev_header_hash = block.prev_header_hash
        # TODO add ledger
        self.ledger = None

class BlockChain:
    # chain is a dictionary, key is hash header, value is the header metadata of blocks
    chain = dict()
    TARGET = b"\x00\x00\x0f\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff"
    last_hash = None
    # Cleaned keys is an ordered list of all the header hashes, only updated on BlockChain.resolve() call
    cleaned_keys = []
    # Target average time in seconds
    target_average_time = 3.5
    # difficulty_constant not used yet
    difficulty_constant = None
    # difficulty_interval is the difficulty check per X number of blocks
    difficulty_interval = 5
    # difficulty multiplier, ensures difficulty change is linear
    difficulty_multiplier = 1

    def network_add(self, block):
        # Checks if block received by networks is valid before adding
        # TODO So right, this one needs to have a caching thing? idk now it just accepts all blocks HUAN AN SOLVE THANKS

        # Idea why not no caching, just check all blocks? Like what if we move the checks to the resolve function?
        # Like, what if network add doesn't really care if a TX is valid, only when validate is called, then it checks EVERYTHING, may be ineffecient
        # But it gets us the points?

        # Validation should be here ah coz this is for all 'network' blocks
        # the add and validate functions are for local blocks, so i just assume all is correct alr
        # What should this check?
        # 1. All transactions are valid, so, idk need to work this out with Youngmin ASAP, but like
        #    assuming all the blocks have their own ledger, you need to double check the prev_header_hash
        #    and check that ledger to see if the account has enough money
        # 2. You also need to check TXID is not duplicated for any blocks before this one, rmb if its
        #    after this block, aka tthis is a fork, it CAN be duplicated
        #
        # After all these verifications,  51% attack and selfish mining should be okay
        # The list of headers in order is cleaned_keys btw, if its not working as intended, just call resolve
        if True:
            self.chain[binascii.hexlify(block.header_hash()).decode()] = block
            return True
        else:
            return False

    def add(self, block):
        # Checks if block is valid before adding
        if self.validate(block):
            self.chain[binascii.hexlify(block.header_hash()).decode()] = block
            return True
        else:
            return False

    def validate(self, block):
        if len(self.chain) > 0:
            # Checks for previous header and target value
            check_previous_header = block.previous_header_hash in self.chain or block.previous_header_hash is None
            check_target = block.header_hash() < self.TARGET
            # print(check_previous_header, check_target)
            return check_previous_header and check_target
        else:
            # If Genesis block, there is no need to check for the last hash value
            return block.header_hash() < self.TARGET

    def resolve(self):
        if len(self.chain) > 0:
            longest_chain_length = 0
            for hash_value in self.chain:
                if self.chain[hash_value].previous_header_hash == None:
                    # Find the genesis block's hash value
                    genesis_hash_value = hash_value
                    # Start DP function
                    temp_cleaned_keys = self.resolve_DP(
                        genesis_hash_value, 0, [genesis_hash_value])[1]
                    if len(temp_cleaned_keys) > longest_chain_length:
                        self.cleaned_keys = copy.deepcopy(temp_cleaned_keys)
                        longest_chain_length = len(temp_cleaned_keys)
            try:
                self.last_hash = self.cleaned_keys[-1]
            except IndexError:
                self.last_hash = None

    def resolve_DP(self, hash_check, score, cleared_hashes):
        # Assuming this is the last block in the chain, it first saves itself to the list
        list_of_linked_hashes = [(score, cleared_hashes)]
        # Scans the chain for a block with previous_header of the header of the previous block that called the DP
        for hash_value in self.chain:
            if self.chain[hash_value].previous_header_hash == hash_check:
                new_cleared_hashes = copy.deepcopy(cleared_hashes)
                new_cleared_hashes.append(hash_value)
                # Increase score and list of cleared_hashes whenever the DP is called
                list_of_linked_hashes.append(self.resolve_DP(
                    hash_value, score + 1, new_cleared_hashes))
        # Scans the list_of_linked_hashes and only return the longest chain
        highest_score = 0
        for i in list_of_linked_hashes:
            if i[0] > highest_score:
                highest_score = i[0]
        for i in list_of_linked_hashes:
            if i[0] == highest_score:
                return i

    # Returns the last block in the chain
    def last_block(self):
        self.resolve()
        if self.last_hash is not None:
            return self.chain[self.last_hash]
        else:
            return None

    def __str__(self):
        reply = "-----------------\nThere are {} blocks in the blockchain\n\n".format(
            len(self.chain))
        for count, i in enumerate(self.chain):
            reply += "Header: {}\tPrev_header: {}\n".format(
                str(i), str(self.chain[i].previous_header_hash))
        reply+="\n~~~\n"
        reply += "The longest chain is {} blocks\n".format(
            len(self.cleaned_keys))
        for count, i in enumerate(self.cleaned_keys):
            reply += i[:10] + " -> "
        reply = reply[:-4]
        return reply

    # REMOVED DIFFICULTY as cannot sync across miners

    # def difficulty_adjust(self):
    #     # Length of TARGET byte object
    #     TARGET_length = 16
    #     # Because we are basing on cleaned_keys list, we need to make sure chain and cleaned_list are the same
    #     self.resolve()
    #     no_of_blocks = len(self.cleaned_keys)
    #     # Every X number of blocks, run difficulty check
    #     if no_of_blocks % self.difficulty_interval == 0 and no_of_blocks > 0:
    #         if no_of_blocks >= self.difficulty_interval:
    #             # Get average time difference across X number of blocks
    #             time_diff = float(self.chain[self.cleaned_keys[-1]].timestamp) - \
    #                 float(self.chain[self.cleaned_keys[-5]].timestamp)
    #             average_time = time_diff/self.difficulty_interval
    #             # Change target depending on how the time average
    #             TARGET_int = int.from_bytes(self.TARGET, 'big')
    #             TARGET_int += int((self.target_average_time -
    #                                average_time) * self.difficulty_multiplier)
    #             # todo limits and max/min
    #             self.TARGET = TARGET_int.to_bytes(16, 'big')
    #             print("Target adjusted:" + str(self.TARGET))


# Test
def main():
    # Create blockchain
    blockchain = BlockChain()

    # Genesis block
    merkletree = MerkleTree()
    for i in range(100):
        merkletree.add(random.randint(100, 1000))
    merkletree.build()
    current_time = str(time.time())
    for nonce in range(10000000):
        block = Block(merkletree, None, merkletree.get_root(),
                      current_time, nonce)
        # If the add is successful, stop loop
        if blockchain.add(block):
            break
    print(blockchain)

    # Other blocks (non-linear)
    for i in range(6):
        merkletree = MerkleTree()
        for i in range(100):
            merkletree.add(random.randint(100, 1000))
        merkletree.build()
        current_time = str(time.time())
        last_hash = random.choice(
            list(blockchain.chain.keys()))
        for nonce in range(10000000):
            block = Block(merkletree, last_hash,
                          merkletree.get_root(), current_time, nonce)
            if blockchain.add(block):
                # If the add is successful, stop loop
                break
        print(blockchain)

    blockchain.resolve()
    print("Done resolve")
    print(blockchain)


if __name__ == '__main__':
    main()
