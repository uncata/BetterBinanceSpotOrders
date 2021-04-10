# BetterBinanceSpotOrders
Place multiple buy orders in a range of the same order size or increasing order size for Binance Spot

##Prerequisites
BetterBinanceSpotOrders needs the following python3 modules:
```
hashlib
hmac
math
requests
time
urllib.parse
```

##Place Buy Orders (Same Order Size)
```python
place_buyOrders("ADAUSDT", 1.2, 1, 1000, 0)
```

##Place Buy Orders (Increasing Order Size)
```python
place_buyOrders("ADAUSDT", 1.2, 1, 1000, 50)
```
The last parameter *increaseAmount* is the percent each order is increased by if you were to place 10 orders. For example, you would enter *50* if you want to increase each order by 50%. The *increaseAmount* percentage is adjusted for the actual number of orders that will be placed. 


##Cancel All Orders for a Symbol
```python
cancel_Orders("ADAUSDT")
```
