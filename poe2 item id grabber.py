import json

curr="gems"



with open(f"resp_{curr}.json", "r") as file:
    data = json.load(file)

currencies = {}
for entry in data["items"]:
    currencies[entry["apiId"]] = {
            "itemId": entry["itemId"]
        }
    

print(currencies)
file.close()
file = open(f"resp_{curr}.json", "w")
file.write(json.dumps(currencies, indent=4))
file.close()