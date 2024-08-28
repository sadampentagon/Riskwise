from flask import Flask, request, jsonify
import mysql.connector
from datetime import datetime, timedelta

app = Flask(__name__)

# Database connection configuration
db_config = {
    'user': 'root',
    'password': '',  # Ensure your actual password is set here
    'host': 'localhost',
    'database': 'trading'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Profit Calculator</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            color: #333;
        }
        .container {
            background-color: #fff;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            padding: 20px;
            max-width: 500px;
            width: 100%;
            text-align: center;
        }
        h1 {
            color: #007bff;
            margin-bottom: 20px;
        }
        label {
            font-size: 1.2em;
        }
        input[type="date"] {
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 5px;
            width: calc(100% - 22px);
            margin-bottom: 20px;
            font-size: 1em;
        }
        button {
            background-color: #007bff;
            color: #fff;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1em;
        }
        button:hover {
            background-color: #0056b3;
        }
        #result {
            margin-top: 20px;
            text-align: left;
        }
        #result h2 {
            color: #28a745;
            font-size: 1.5em;
        }
        #result ul {
            list-style-type: none;
            padding: 0;
        }
        #result li {
            background-color: #e9ecef;
            margin-bottom: 10px;
            padding: 10px;
            border-radius: 5px;
            font-size: 1.1em;
        }
        #result h3 {
            margin-top: 20px;
            color: #dc3545;
            font-size: 1.4em;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Profit Calculator</h1>
        <form id="profitForm">
            <label for="date">Enter date:</label>
            <input type="date" id="date" name="date">
            <button type="submit">Calculate Profit</button>
        </form>
        <div id="result"></div>
    </div>
    <script>
        document.getElementById('profitForm').addEventListener('submit', function(event) {
            event.preventDefault();
            const date = document.getElementById('date').value;
            fetch(`/profit?date=${date}`)
                .then(response => response.json())
                .then(data => {
                    const resultDiv = document.getElementById('result');
                    resultDiv.innerHTML = '';
                    if (data.error) {
                        resultDiv.innerHTML = `<p style="color: red;">${data.error}</p>`;
                    } else {
                        let totalProfit = 0;
                        let resultHtml = `<h2>Profit Calculation on ${date}</h2><ul>`;
                        for (const [isin, profit] of Object.entries(data)) {
                            resultHtml += `<li>ISIN: ${isin}, Profit: ${profit.toFixed(2)}</li>`;
                            totalProfit += profit;
                        }
                        resultHtml += '</ul>';
                        resultHtml += `<h3>Total Profit on ${date}: ${totalProfit.toFixed(2)}</h3>`;
                        resultDiv.innerHTML = resultHtml;
                    }
                })
                .catch(error => {
                    console.error('Error fetching profit:', error);
                    document.getElementById('result').innerHTML = 
                        '<p style="color: red;">An error occurred while fetching profit.</p>';
                });
        });
    </script>
</body>
</html>
'''

@app.route('/profit', methods=['GET'])
def calculate_profit():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"error": "Date parameter is required"}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch sell trades for the specified date
        cursor.execute("""
            SELECT ISIN, Quantity, Price, `Order Execution Time`
            FROM sheet 
            WHERE `Trade Date` = %s AND `Trade Type` = 'sell'
        """, (date,))
        sell_trades = cursor.fetchall()

        if not sell_trades:
            return jsonify({"error": "No sell trades found for the given date"}), 404

        profit = {}

        for sell_trade in sell_trades:
            total_profit = calculate_trade_profit(cursor, sell_trade, date)
            profit[sell_trade['ISIN']] = profit.get(sell_trade['ISIN'], 0) + total_profit

        cursor.close()
        conn.close()

        return jsonify(profit)
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def calculate_trade_profit(cursor, sell_trade, sell_date):
    """Calculate profit for a given sell trade by traversing the corresponding buy trades."""
    sell_qty = float(sell_trade['Quantity'])
    sell_price = float(sell_trade['Price'])
    sell_time = sell_trade['Order Execution Time']
    remaining_qty = sell_qty
    total_profit = 0
    current_date = sell_date

    while remaining_qty > 0:
        cursor.execute("""
            SELECT Quantity, Price, `Order Execution Time`
            FROM sheet 
            WHERE ISIN = %s AND `Trade Type` = 'buy' AND `Trade Date` = %s
        """, (sell_trade['ISIN'], current_date))
        buy_trades = cursor.fetchall()

        for buy_trade in buy_trades:
            buy_qty = float(buy_trade['Quantity'])
            buy_price = float(buy_trade['Price'])
            buy_time = buy_trade['Order Execution Time']

            if current_date == sell_date and buy_time >= sell_time:
                continue

            matched_qty = min(remaining_qty, buy_qty)
            total_profit += (sell_price - buy_price) * matched_qty
            remaining_qty -= matched_qty

            if remaining_qty == 0:
                break
                #forward traversal
        if remaining_qty > 0 and current_date == sell_date:
            for buy_trade in buy_trades:
                if buy_trade['Order Execution Time'] > sell_time:
                    matched_qty = min(remaining_qty, float(buy_trade['Quantity']))
                    total_profit += (sell_price - float(buy_trade['Price'])) * matched_qty
                    remaining_qty -= matched_qty

                    if remaining_qty == 0:
                        break

        current_date -= timedelta(days=1)
        if current_date < datetime(2000, 1, 1).date():
            break

    return total_profit

if __name__ == '__main__':
    app.run(debug=True, port=5001)
