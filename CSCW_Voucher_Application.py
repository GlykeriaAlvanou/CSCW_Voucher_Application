from flask import Flask
from flask import request
from flask import jsonify
from flask import json
from bigchaindb import Bigchain
from bigchaindb import crypto
from flask_restful import reqparse
import rethinkdb as r
import time
from enum import Enum

app = Flask(__name__)


class UserAttributes(Enum):
    PUBLIC_KEY = "public_key"
    PRIVATE_KEY = "private_key"
    USERNAME = "username"
    PASSWORD = "password"
    TYPE = "type"
    SOURCE_USERNAME = "source_username"
    TARGET_USERNAME = "target_username"


class UserType(Enum):
    DONOR = 1
    CONSUMER = 2
    COMPANY = 3

class Operations(Enum):
    CREATE = "CREATE"
    TRANSFER = "TRANSFER"

class TableNames(Enum):
    USER = "user_table"
    BIGCHAIN = "bigchain"

b = Bigchain()
conn = r.connect("localhost", 28015)


@app.route('/voucherApp/createUser', methods=['POST'])
def createUser():
    # Specifying Mandatory Arguments
    parser = reqparse.RequestParser()
    parser.add_argument(UserAttributes.USERNAME.value,required=True, type=str)
    parser.add_argument(UserAttributes.PASSWORD.value, required=True, type=str)
    parser.add_argument(UserAttributes.TYPE.value, required=True, type=str)

    username = request.get_json(force=False)[UserAttributes.USERNAME.value]
    password = request.get_json(force=False)[UserAttributes.PASSWORD.value]
    type = request.get_json(force=False)[UserAttributes.TYPE.value]


    if(not checkIfTheUserExists(username)):
        user_priv, user_pub = crypto.generate_key_pair()
        userTuple = constructUserTuple(username,password,type,user_pub,user_priv)
        insertData(TableNames.USER.value,userTuple)
        return jsonify(status="success",publicKey=user_pub,privateKey=user_priv)
    else:
        return jsonify(status="error", errorMessage="Username Already Exists!")


@app.route('/voucherApp/signIn',methods=['POST'])
def signIn():
    # Specifying Mandatory Arguments
    parser = reqparse.RequestParser()
    parser.add_argument(UserAttributes.USERNAME.value, required=True, type=str)
    parser.add_argument(UserAttributes.PASSWORD.value, required=True, type=str)

    username = request.get_json(force=False)[UserAttributes.USERNAME.value]
    password = request.get_json(force=False)[UserAttributes.PASSWORD.value]

    if(checkIfTheUserExists(username)):
        tupleData = getTupleFromDB(TableNames.USER.value,username)
        if(tupleData[UserAttributes.PASSWORD.value] == password):
            return jsonify(status="success",publicKey=tupleData[UserAttributes.PUBLIC_KEY.value],privateKey=tupleData[UserAttributes.PRIVATE_KEY.value])
        else:
            return jsonify(status="error",errorMessage="Password Incorrect!")
    else:
        return jsonify(status="error", errorMessage="User doesn't exist!")


@app.route('/voucherApp/createVoucher',methods=['POST'])
def createVoucher():
    # Specifying Mandatory Arguments
    parser = reqparse.RequestParser()
    parser.add_argument(UserAttributes.USERNAME.value, required=True, type=str)
    parser.add_argument('value', required=True, type=str)
    parser.add_argument('voucher_name', required=True, type=str)


    voucherName = request.get_json(force=False)['voucher_name']
    username = request.get_json(force=False)[UserAttributes.USERNAME.value]
    value = request.get_json(force=False)['value']

    if(not checkIfTheUserExists(username)):
        return jsonify(status="error", errorMessage="User doesn't exist!")
    else:
        voucherPayload = {}
        voucherPayload["name"] = voucherName
        voucherPayload["value"] = value
        user_pub_key = getTupleFromDB(TableNames.USER.value,username)[UserAttributes.PUBLIC_KEY.value]
        tx = b.create_transaction(b.me, user_pub_key, None, Operations.CREATE.value, payload=voucherPayload)
        tx_signed = b.sign_transaction(tx, b.me_private)
        b.write_transaction(tx_signed)
        time.sleep(5)
        return jsonify(status="success",message="Voucher Created Successfully")


@app.route('/voucherApp/getOwnedIDs',methods=['GET'])
def getOwnedIDs():
    # Specifying Mandatory Arguments
    parser = reqparse.RequestParser()
    parser.add_argument(UserAttributes.USERNAME.value, required=True, type=str)

    username = request.args.get(UserAttributes.USERNAME.value)
    if (not checkIfTheUserExists(username)):
        return jsonify(status="error", errorMessage="User doesn't exist!")
    else:
        user_pub_key = getTupleFromDB(TableNames.USER.value, username)[UserAttributes.PUBLIC_KEY.value]
        return jsonify(data = b.get_owned_ids(user_pub_key))


@app.route('/voucherApp/transferVoucher',methods=['POST'])
def transferVoucher():
    # Specifying Mandatory Arguments
    parser = reqparse.RequestParser()
    parser.add_argument(UserAttributes.TARGET_USERNAME.value, required=True, type=str)
    parser.add_argument(UserAttributes.SOURCE_USERNAME.value, required=True, type=str)
    parser.add_argument(UserAttributes.PRIVATE_KEY.value, required=True, type=str)
    parser.add_argument('asset_id', required=True, type=str)


    source_username = request.get_json(force=False)[UserAttributes.SOURCE_USERNAME.value]
    target_username = request.get_json(force=False)[UserAttributes.TARGET_USERNAME.value]
    sourceuser_priv_key = request.get_json(force=False)[UserAttributes.PRIVATE_KEY.value]
    asset_id = request.get_json(force=False)['asset_id']
    if (not checkIfTheUserExists(target_username)):
        return jsonify(status="error", errorMessage="Target User doesn't exist!")
    elif(not checkIfTheUserExists(source_username)):
        return jsonify(status="error", errorMessage="Source User doesn't exist!")
    else:
        target_user_pub_key = getTupleFromDB(TableNames.USER.value, target_username)[UserAttributes.PUBLIC_KEY.value]
        source_user_pub_key = getTupleFromDB(TableNames.USER.value, source_username)[UserAttributes.PUBLIC_KEY.value]
        print(sourceuser_priv_key)
        tx = {}
        tx["txid"] = asset_id
        tx["cid"] = 0
        tx_transfer = b.create_transaction(source_user_pub_key, target_user_pub_key, tx, Operations.TRANSFER.value)
        tx_transfer_signed = b.sign_transaction(tx_transfer, sourceuser_priv_key)
        b.write_transaction(tx_transfer_signed)
        time.sleep(5)
        return jsonify(status="success", errorMessage="Voucher Successfully Trasferred")


# Following are the utility methods

def checkIfTheUserExists(userName):
    return_data = r.db("bigchain").table(TableNames.USER.value).get(userName).count().default(0).run(conn)
    if(return_data >0):
        return True
    else:
        return False


def constructUserTuple(username, password, type, public_key,private_key):
    data = {}
    data[UserAttributes.USERNAME.value] = username
    data[UserAttributes.PASSWORD.value] = password
    data[UserAttributes.TYPE.value] = type
    data[UserAttributes.PUBLIC_KEY.value] = public_key
    data[UserAttributes.PRIVATE_KEY.value] = private_key
    return data

def getTupleFromDB(tableName,primary_key):
    return r.db("bigchain").table(tableName).get(primary_key).run(conn)

def insertData(tableName,data):
    r.db("bigchain").table(tableName).insert(data).run(conn)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)



