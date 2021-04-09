import requests
import math

import hmac
import time
import hashlib
from urllib.parse import urlencode, quote

from Keys import KEY, SECRET

BASE_URL = 'https://api.binance.com'

def get_signature(query_string):
    return hmac.new(SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

def get_timestamp():
    return int(time.time() * 1000)

def dispatch_request(http_method):
    session = requests.Session()
    session.headers.update({
        'Content-Type': 'application/json;charset=utf-8',
        'X-MBX-APIKEY': KEY
    })
    return {
        'GET': session.get,
        'DELETE': session.delete,
        'PUT': session.put,
        'POST': session.post,
    }.get(http_method, 'GET')

#used for sending signed data request
def send_signed_request(http_method, url_path, payload={}):
    query_string = urlencode(payload)
    query_string = query_string.replace('%27', '%22')

    if query_string:
        query_string = "{}&timestamp={}".format(query_string, get_timestamp())
    else:
        query_string = 'timestamp={}'.format(get_timestamp())

    url = BASE_URL + url_path + '?' + query_string + '&signature=' + get_signature(query_string)
    print(url)
    params = {'url': url, 'params': {}}
    response = dispatch_request(http_method)(**params)
    return response.json()

# used for sending public data request
def send_public_request(url_path, payload={}):
    query_string = urlencode(payload, True)
    url = BASE_URL + url_path
    if query_string:
        url = url + '?' + query_string
    print("{}".format(url))
    response = dispatch_request('GET')(url=url)
    return response.json()

def roundDown(number, places):
    return math.floor(number * (10 ** places)) / (10 ** places)

def roundUp(number, places):
    return math.ceil(number * (10 ** places)) / (10 ** places)

def get_maxOrders(symbol, firstEntry, lastEntry, tradeAmount, pricePrecision, quantityPrecision, firstEntryMinQty, increaseAmount, maxNumOrders):
    denominator = []

    for a in range(2, maxNumOrders + 1):
        increase_amount = ((((1 + (increaseAmount / 100))**9)**(1/(a-1))) - 1)*100

        for b in range(a):
            denominator.append((1 + (increase_amount / 100)) ** b)

        firstOrderQuantity = roundDown((tradeAmount / sum(denominator)) / firstEntry, quantityPrecision)
        firstOrderSize = roundDown(firstOrderQuantity * firstEntry, pricePrecision)

        #print("If {} orders are placed, then first order size will be {} USDT and first order quantity will be {} {}".format(a, firstOrderSize, firstOrderQuantity, symbol.split("USDT")[0]))
        #print(increase_amount)
        denominator.clear()

        if (firstOrderQuantity == 0) and (a == 2):
            return 0

        elif (firstOrderQuantity < firstEntryMinQty) and (a == 2):
            return 0

        elif firstOrderQuantity < firstEntryMinQty:
            return a - 1

    return maxNumOrders

def get_symbolInfo(symbol, firstEntry, lastEntry, tradeAmount, increaseAmount):

    symbols = send_public_request('/api/v3/exchangeInfo')["symbols"]

    #loop through list and check key for match
    for a in range(len(symbols)):

        #if the symbol is in the list with the key then assign values
        if symbol == symbols[a]["symbol"]:
            pricePrecision = symbols[a]["quotePrecision"]
            quantityPrecision = symbols[a]["baseAssetPrecision"]
            MIN_NOTIONAL = float(symbols[a]["filters"][3]["minNotional"])
            minQty = float(symbols[a]["filters"][2]["minQty"])
            firstEntryMinQty = max(roundUp(MIN_NOTIONAL / firstEntry, quantityPrecision), minQty)
            firstEntryMinSize = roundDown(firstEntry * firstEntryMinQty, pricePrecision)
            maxNumOrders = symbols[a]["filters"][6]["maxNumOrders"] - symbols[a]["filters"][7]["maxNumAlgoOrders"]
            maxOrders = get_maxOrders(symbol, firstEntry, lastEntry, tradeAmount, pricePrecision, quantityPrecision, firstEntryMinQty, increaseAmount, maxNumOrders)
            
            break

        #otherwise make it "n/a"
        else:
            pricePrecision = "n/a"
            quantityPrecision = "n/a"
            MIN_NOTIONAL = "n/a"
            minQty = "n/a"
            firstEntryMinQty = "n/a"
            firstEntryMinSize = "n/a"
            maxOrders = 0
            maxNumOrders = 0
            
    return {"pricePrecision": pricePrecision, "quantityPrecision": quantityPrecision, "firstEntryPrice": firstEntry, "firstEntryMinQty": firstEntryMinQty, "firstEntryMinSize": firstEntryMinSize, "maxOrders": maxOrders, "maxNumOrders": maxNumOrders}

def place_buyOrders(symbol, firstEntry, lastEntry, tradeAmount, increaseAmount):
    
    data = get_symbolInfo(symbol, firstEntry, lastEntry, tradeAmount, increaseAmount)

    pricePrecision = data["pricePrecision"]
    quantityPrecision = data["quantityPrecision"]
    firstEntryMinQty = data["firstEntryMinQty"]
    maxNumOrders = data["maxNumOrders"]

    numberOfOrders = get_maxOrders(symbol, firstEntry, lastEntry, tradeAmount, pricePrecision, quantityPrecision, firstEntryMinQty, increaseAmount, maxNumOrders)

    percent = - 100 * (lastEntry / firstEntry) ** (1 / (numberOfOrders - 1)) + 100
    percentIncrease = ((((1 + (increaseAmount / 100)) ** 9) ** (1 / (numberOfOrders - 1))) - 1) * 100

    denominator = []

    for i in range(numberOfOrders):
        denominator.append((1 + (percentIncrease / 100)) ** i)

    firstOrderQuantity = roundDown((tradeAmount / sum(denominator)) / firstEntry, quantityPrecision)
    firstOrderSize = round(firstOrderQuantity * firstEntry, pricePrecision)

    entryPrices = [firstEntry]
    thisEntryPrice = firstEntry

    orderQuantities = [firstOrderQuantity]

    orderSizes = [firstOrderSize]
    thisOrderSize = firstOrderSize

    for j in range(numberOfOrders - 1):
        entryPrices.append(round(thisEntryPrice * (1 - (percent / 100)), pricePrecision))      
        orderQuantities.append(roundDown((thisOrderSize * (1 + (percentIncrease / 100))) / (thisEntryPrice * (1 - (percent / 100))), quantityPrecision))
        orderSizes.append(round(entryPrices[j + 1] * orderQuantities[j + 1], pricePrecision))

        thisEntryPrice = thisEntryPrice * (1 - (percent / 100))
        thisOrderSize = thisOrderSize * (1 + (percentIncrease / 100))

    print("{} orders to be placed are".format(numberOfOrders))

    for k in range(numberOfOrders):
        params = {
            "symbol": symbol,
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": orderQuantities[k],
            "price": str(entryPrices[k]),
        }

        print(params)
        #response = send_signed_request('POST', 'api/v3/order', params)
        #print(response)

    print("Total order size is {} USDT".format(roundDown(sum(orderSizes), pricePrecision))) #total trade size

    print("Average entry price is {}, if all orders are filled".format(roundDown(sum(orderSizes)/sum(orderQuantities), pricePrecision))) #average entry if all orders are filled

def cancelOrders(symbol):
    send_signed_request('DELETE', '/api/v3/openOrders', {"symbol": symbol})

place_buyOrders("ADAUSDT", 1.2, 1, 1235, 0)