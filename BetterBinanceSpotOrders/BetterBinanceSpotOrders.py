import hashlib
import hmac
import math
import requests
import time
from urllib.parse import urlencode, quote

from Keys import KEY, SECRET 

BASE_URL = 'https://api.binance.com' # base endpoint for Binance Spot

# get signature string
def get_signature(query_string):
    return hmac.new(SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

# get local timestamp
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

# used for sending signed data request
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

# round down a number to specified decimal places
def roundDown(number, places):
    return math.floor(number * (10 ** places)) / (10 ** places)

# round up a number to specified decimal places
def roundUp(number, places):
    return math.ceil(number * (10 ** places)) / (10 ** places)

def get_maxOrders(symbol, firstEntry, lastEntry, tradeAmount, pricePrecision, quantityPrecision, firstEntryMinQty, increaseAmount, maxNumOrders):
    denominator = []

    for a in range(2, maxNumOrders + 1):
        equivalentPercentIncrease = ((((1 + (increaseAmount / 100))**9)**(1/(a-1))) - 1)*100 # a >= 2, or else undefined, therefore minimum of 2 valid orders

        for b in range(a):
            denominator.append((1 + (equivalentPercentIncrease / 100)) ** b)

        firstOrderQuantity = roundDown((tradeAmount / sum(denominator)) / firstEntry, quantityPrecision)
        firstOrderSize = roundDown(firstOrderQuantity * firstEntry, pricePrecision)

        denominator.clear()

        if ((firstOrderQuantity == 0) and (a == 2)):
            return 0

        elif ((firstOrderQuantity < firstEntryMinQty) and (a == 2)):
            return 0

        elif firstOrderQuantity < firstEntryMinQty:
            return a - 1

    return maxNumOrders

# get dictionary of important symbol information required for calculating orders
def get_symbolInfo(symbol, firstEntry, lastEntry, tradeAmount, increaseAmount):

    symbols = send_public_request('/api/v3/exchangeInfo')["symbols"] 

    for a in range(len(symbols)):

        if symbol == symbols[a]["symbol"]:
            quantityPrecision = symbols[a]["baseAssetPrecision"]
            pricePrecision = symbols[a]["quotePrecision"]
            minQty = float(symbols[a]["filters"][2]["minQty"])
            minNotional = float(symbols[a]["filters"][3]["minNotional"])
            maxNumOrders = symbols[a]["filters"][6]["maxNumOrders"] - symbols[a]["filters"][7]["maxNumAlgoOrders"]
            firstEntryMinQty = max(roundUp(minNotional / firstEntry, quantityPrecision), minQty)
            firstEntryMinSize = roundDown(firstEntry * firstEntryMinQty, pricePrecision)
            maxOrders = get_maxOrders(symbol, firstEntry, lastEntry, tradeAmount, pricePrecision, quantityPrecision, firstEntryMinQty, increaseAmount, maxNumOrders)
            
            break

        else:
            quantityPrecision = "n/a"
            pricePrecision = "n/a"
            minQty = "n/a"
            minNotional = "n/a"
            maxNumOrders = 0
            firstEntryMinQty = "n/a"
            firstEntryMinSize = "n/a"
            maxOrders = 0
            
            
    return {"pricePrecision": pricePrecision, "quantityPrecision": quantityPrecision, "firstEntryPrice": firstEntry, "firstEntryMinQty": firstEntryMinQty, "firstEntryMinSize": firstEntryMinSize, "maxOrders": maxOrders, "maxNumOrders": maxNumOrders}

# Place multiple buy orders within a range, if increaseAmount is 0 then all orders will be of the same size. 
# The increaseAmount is a percentage that you want to increase each order by if you placed 10 orders. It is then adjusted for the actual number of orders calculated from get_maxOrders
def place_buyOrders(symbol, firstEntry, lastEntry, tradeAmount, increaseAmount):
    
    symbolInfo = get_symbolInfo(symbol, firstEntry, lastEntry, tradeAmount, increaseAmount)

    pricePrecision = symbolInfo["pricePrecision"]
    quantityPrecision = symbolInfo["quantityPrecision"]
    firstEntryMinQty = symbolInfo["firstEntryMinQty"]
    maxNumOrders = symbolInfo["maxNumOrders"]
    numberOfOrders = get_maxOrders(symbol, firstEntry, lastEntry, tradeAmount, pricePrecision, quantityPrecision, firstEntryMinQty, increaseAmount, maxNumOrders)
    percentBetweenEntries = - 100 * (lastEntry / firstEntry) ** (1 / (numberOfOrders - 1)) + 100
    equivalentPercentIncrease = ((((1 + (increaseAmount / 100)) ** 9) ** (1 / (numberOfOrders - 1))) - 1) * 100

    denominator = []

    for a in range(numberOfOrders):
        denominator.append((1 + (equivalentPercentIncrease / 100)) ** a)

    firstOrderQuantity = roundDown((tradeAmount / sum(denominator)) / firstEntry, quantityPrecision)
    firstOrderSize = round(firstOrderQuantity * firstEntry, pricePrecision)

    entryPrices = [firstEntry]
    thisEntryPrice = firstEntry

    orderQuantities = [firstOrderQuantity]

    orderSizes = [firstOrderSize]
    thisOrderSize = firstOrderSize

    for b in range(numberOfOrders - 1):
        entryPrices.append(round(thisEntryPrice * (1 - (percentBetweenEntries / 100)), pricePrecision))      
        orderQuantities.append(roundDown((thisOrderSize * (1 + (equivalentPercentIncrease / 100))) / (thisEntryPrice * (1 - (percentBetweenEntries / 100))), quantityPrecision))
        orderSizes.append(round(entryPrices[b + 1] * orderQuantities[b + 1], pricePrecision))
        thisEntryPrice = thisEntryPrice * (1 - (percentBetweenEntries / 100))
        thisOrderSize = thisOrderSize * (1 + (equivalentPercentIncrease / 100))

    print("{} orders to be placed are".format(numberOfOrders))

    for c in range(numberOfOrders):
        params = {
            "symbol": symbol,
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": orderQuantities[c],
            "price": str(entryPrices[c]),
        }

        print(params)
        send_signed_request('POST', 'api/v3/order', params)

    print("Total order size is {} USDT".format(roundDown(sum(orderSizes), pricePrecision))) #total trade size

    print("Average entry price is {}, if all orders are filled".format(roundDown(sum(orderSizes)/sum(orderQuantities), pricePrecision))) #average entry if all orders are filled

# cancel orders for a given symbol
def cancel_Orders(symbol):
    send_signed_request('DELETE', '/api/v3/openOrders', {"symbol": symbol})

# example order for same order sizes
#place_buyOrders("ADAUSDT", 1.2, 1, 1000, 0)

# example order for increasing order sizes
#place_buyOrders("ADAUSDT", 1.2, 1, 1000, 50)