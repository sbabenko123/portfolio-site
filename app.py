from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response
import mysql.connector
from mysql.connector import IntegrityError
import secrets
from metaphor_python import Metaphor
import requests
import random
import yfinance as yf
from datetime import date,timedelta
from decimal import Decimal
from io import BytesIO
from reportlab.pdfgen import canvas

app = Flask(__name__, static_url_path='/static')
app.secret_key = secrets.token_hex(16)
metaphor = Metaphor("eb196ce4-349c-4969-b741-4134c8e58e22")

def metaSearch(query):
    response = metaphor.search( query, num_results=3,use_autoprompt=True)
    return response

def metaSimilar(url):
    response = metaphor.find_similar(url, num_results=3)
    return response


def get_user_id():
    return session.get('user_id', -1)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    # Retrieve the user_id from the session
    user_id = session.get('user_id')

    if user_id is not None:
        # Fetch data for the logged-in user using user_id
        try:
            # Fetch the user's portfolios from the database
            with mysql.connector.connect(
                    host="DESKTOP-SDJEFAT",
                    user="sofia",
                    password="plokijuh",
                    database="ai_news"
            ) as db:
                cursor = db.cursor()
                cursor.execute('SELECT * FROM portfolios WHERE user_id = %s', (user_id,))
                portfolios = cursor.fetchall()

        except mysql.connector.Error as err:
            print(f"Error: {err}")
            return "Error fetching portfolios. Please try again later."

        return render_template('dashboard.html', user_id=user_id, portfolios=portfolios)
    else:
        # Redirect to login if user is not logged in
        return redirect(url_for('login'))




@app.route('/add_portfolio', methods=['POST'])
def add_portfolio():
    # Access form data
    portfolio_name = request.form.get('portfolio_name')
    portfolio_objective = request.form.get('portfolio_objective')
    initial_deposit = request.form.get('initial_deposit')

    # Perform validation if needed

    # Insert the new portfolio into the database
    try:
        with mysql.connector.connect(
            host="DESKTOP-SDJEFAT",
            user="sofia",
            password="plokijuh",
            database="ai_news"
        ) as db:
            cursor = db.cursor()
            cursor.execute('INSERT INTO portfolios (user_id, portfolio_name, portfolio_objective, initial_deposit, cash_balance) VALUES (%s, %s, %s, %s, %s)',
                           (get_user_id(), portfolio_name, portfolio_objective, initial_deposit, initial_deposit))
            
            db.commit()

        return redirect(url_for('dashboard'))

    except IntegrityError as ie:
        # Handle integrity error (if needed)
        return "Error creating the portfolio. Please try again."

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error creating the portfolio. Please try again later."
    

@app.route('/view_portfolio', methods=['GET', 'POST'])
def view_portfolio():
    portfolio_id = request.args.get('portfolio_id')
    session['portfolio_id'] = portfolio_id
    return redirect(url_for('portfolio', portfolio_id=portfolio_id))



@app.route('/portfolio', methods=['GET'])
def portfolio():
    portfolio_id = session.get('portfolio_id')    
    # Fetch the portfolio from the database
    try:
        with mysql.connector.connect(
            host="DESKTOP-SDJEFAT",
            user="sofia",
            password="plokijuh",
            database="ai_news"
        ) as db:
            cursor = db.cursor()
            cursor.execute('SELECT * FROM portfolios WHERE id = %s', (portfolio_id,))
            portfolio = cursor.fetchone()

            # Fetch the holdings for the portfolio
            cursor.execute('SELECT * FROM holdings WHERE portfolio_id = %s', (portfolio_id,))
            holdings = cursor.fetchall()

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error fetching the portfolio. Please try again later."

    return render_template('portfolio.html', portfolio=portfolio, holdings=holdings)

@app.route('/add_holding', methods=['POST'])
def add_holding():
    # Access form data
    portfolio_id = session.get('portfolio_id')
    stock_symbol = request.form.get('stock_symbol')
    num_shares = request.form.get('num_shares')
    action = request.form.get('action')
    purchase_price = get_current_stock_price(stock_symbol)
    transaction_date = date.today().strftime("%Y-%m-%d")
    if action == 'sell':
        total_cost = purchase_price*int(num_shares)
        num_shares = (-1)*int(num_shares)
    if action == 'buy':
        total_cost = (-1)*purchase_price*int(num_shares)

    try:
        with mysql.connector.connect(
            host="DESKTOP-SDJEFAT",
            user="sofia",
            password="plokijuh",
            database="ai_news"
        ) as db:
            cursor = db.cursor()

            # Assuming you have variables like portfolio_id, stock_symbol, num_shares, purchase_price
            cursor.execute(
                'INSERT INTO holdings (portfolio_id, stock_symbol, num_shares, purchase_price, current_price, profit_loss) VALUES (%s, %s, %s, %s, %s, %s)',
                (portfolio_id, stock_symbol, num_shares, purchase_price, purchase_price, Decimal(0))
            )
            cursor.execute(
                'UPDATE portfolios SET cash_balance = cash_balance + %s WHERE id = %s', (total_cost, portfolio_id)
            )
            cursor.execute(
                'INSERT INTO transactions (portfolio_id, stock_symbol, transaction_type, transaction_date, amount, profit_loss) VALUES (%s, %s, %s, %s, %s, %s)',
                (portfolio_id, stock_symbol, action, transaction_date, total_cost, Decimal(0))
            )

            # Commit the changes to the database
            db.commit()

    except mysql.connector.IntegrityError as e:
        # Check for duplicate entry error
        if e.errno == 1062:
            # Duplicate entry error message
            flash('Error: Duplicate entry. Holding already exists!', 'error')
        else:
            # Handle other integrity errors
            flash(f'Error: {e}', 'error')

    # After processing the form, redirect to the same page
    return redirect(url_for('portfolio'))

@app.route('/get_total_profit_loss/<portfolio_id>', methods=['GET'])
def get_total_profit_loss(portfolio_id):
    try:
        with mysql.connector.connect(
            host="DESKTOP-SDJEFAT",
            user="sofia",
            password="plokijuh",
            database="ai_news"
        ) as db:
            cursor = db.cursor()
            cursor.execute('SELECT SUM(profit_loss) FROM holdings WHERE portfolio_id = %s', (portfolio_id,))
            total_profit_loss = cursor.fetchone()[0]

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error fetching the total profit/loss. Please try again later."

    return jsonify(total_profit_loss)




@app.route('/update_current_price', methods=['POST'])
def update_current_price():
    stock_symbol = request.form.get('stock_symbol')
    current_price = get_current_stock_price(stock_symbol)
    portfolio_id = session.get('portfolio_id')

    # Update the current price in the database
    try:
        with mysql.connector.connect(
            host="DESKTOP-SDJEFAT",
            user="sofia",
            password="plokijuh",
            database="ai_news"
        ) as db:
            cursor = db.cursor()

            # Assuming you have variables like portfolio_id, stock_symbol, num_shares, purchase_price
            cursor.execute('SELECT purchase_price, num_shares FROM holdings WHERE portfolio_id = %s AND stock_symbol = %s', (portfolio_id, stock_symbol))
            purchase_price_result = cursor.fetchone()

            if purchase_price_result:
                # Extract the purchase_price from the result
                purchase_price = purchase_price_result[0]
                num_shares = purchase_price_result[1]

                # Calculate profit_loss
                profit_loss = (Decimal(current_price) - purchase_price)*num_shares

                # Update the holdings table
                cursor.execute(
                    'UPDATE holdings SET current_price = %s, profit_loss = %s WHERE portfolio_id = %s AND stock_symbol = %s',
                    (current_price, profit_loss, portfolio_id, stock_symbol)
                )

                
                # Commit the changes to the database
                db.commit()
            else:
                # Handle the case where purchase_price is not found
                print("Purchase price not found for the specified portfolio and stock symbol.")

    except mysql.connector.Error as err:
        print(f"Error: {err}")

    return redirect(url_for('portfolio'))


@app.route('/cash_out', methods=['GET'])
def cash_out():
    # Get parameters from the request
    portfolio_id = request.args.get('portfolio_id')
    stock_symbol = request.args.get('stock_symbol')

    # Delete the holding from the holdings table and add profit_loss to the portfolio cash_balance
    try:
        with mysql.connector.connect(
            host="DESKTOP-SDJEFAT",
            user="sofia",
            password="plokijuh",
            database="ai_news"
        ) as db:
            cursor = db.cursor()

            # Assuming you have variables like portfolio_id, stock_symbol, num_shares, purchase_price
            cursor.execute('SELECT current_price, num_shares, profit_loss FROM holdings WHERE portfolio_id = %s AND stock_symbol = %s', (portfolio_id, stock_symbol))
            holding_info = cursor.fetchone()

            if holding_info:
                # Extract information from the result
                current_price = holding_info[0]
                num_shares = holding_info[1]
                profit_loss = holding_info[2]

                if num_shares < 0:
                    amount = (-1)*current_price*num_shares
                else:
                    amount = current_price*num_shares

                # Add profit_loss to the portfolio cash_balance
                cursor.execute('UPDATE portfolios SET cash_balance = cash_balance + %s WHERE id = %s', (amount, portfolio_id))

                # Insert the transaction into the transactions table
                cursor.execute(
                    'INSERT INTO transactions (portfolio_id, stock_symbol, transaction_type, transaction_date, amount, profit_loss) VALUES (%s, %s, %s, %s, %s, %s)',
                    (portfolio_id, stock_symbol, 'sell', date.today().strftime("%Y-%m-%d"), amount, profit_loss)
                )

                # Delete the holding from the holdings table
                cursor.execute('DELETE FROM holdings WHERE portfolio_id = %s AND stock_symbol = %s', (portfolio_id, stock_symbol))

                # Commit the changes to the database
                db.commit()
            else:
                # Handle the case where holding information is not found
                print("Holding information not found for the specified portfolio and stock symbol.")

    except mysql.connector.Error as err:
        print(f"Error: {err}")

    return redirect(url_for('portfolio'))


@app.route('/buy_sell', methods=['GET'])
def buy_sell():
    portfolio_id = request.args.get('portfolio_id')
    stock_symbol = request.args.get('stock_symbol')
    action = request.args.get('action')
    num_shares = request.args.get('num_shares')
    purchase_price = get_current_stock_price(stock_symbol)
    transaction_date = date.today().strftime("%Y-%m-%d")
    if action == 'sell':
        total_cost = purchase_price*int(num_shares)
        num_shares = (-1)*int(num_shares)
    if action == 'buy':
        total_cost = (-1)*purchase_price*int(num_shares)

    try:
        with mysql.connector.connect(
            host="DESKTOP-SDJEFAT",
            user="sofia",
            password="plokijuh",
            database="ai_news"
        ) as db:
            cursor = db.cursor()

            cursor.execute(
                'INSERT INTO transactions (portfolio_id, stock_symbol, transaction_type, transaction_date, amount, profit_loss) VALUES (%s, %s, %s, %s, %s, %s)',
                (portfolio_id, stock_symbol, action, transaction_date, total_cost, Decimal(0))
            )

              # Update the holdings table
            cursor.execute(
                'UPDATE holdings SET num_shares = num_shares + %s, purchase_price = ((purchase_price * num_shares) + (%s * %s)) / (num_shares + %s) WHERE portfolio_id = %s AND stock_symbol = %s',
                (num_shares, purchase_price, num_shares, num_shares, portfolio_id, stock_symbol)
            )

            cursor.execute(
                'UPDATE portfolios SET cash_balance = cash_balance + %s WHERE id = %s', (total_cost, portfolio_id)
            )
            

            # Commit the changes to the database
            db.commit()

            return redirect(url_for('portfolio'))

    except mysql.connector.Error as err:
        # Handle the error as needed
        return f"Error: {err}"

@app.route('/get_current_stock_price/<stock_symbol>')
def get_current_stock_price(stock_symbol):
    # Set the start and end date
    start_date = (date.today()-timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = date.today().strftime("%Y-%m-%d")
    
    print(stock_symbol, start_date, end_date)

    # Get the data
    data = yf.download(stock_symbol, start_date, end_date)

    current_price = data['Close'][-1]
    return Decimal(float(current_price))


@app.route('/download_transactions_pdf', methods=['GET'])
def download_transactions_pdf():
    # Get the search query from the request
    search_query = request.args.get('search_query')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    action = request.args.get('action')
    print(search_query, start_date, end_date)

    # Fetch the transactions from the database for the logged-in user
    try:
        with mysql.connector.connect(
                host="DESKTOP-SDJEFAT",
                user="sofia",
                password="plokijuh",
                database="ai_news"
        ) as db:
            cursor = db.cursor()

            # Assuming you have a user_id stored in the session
            user_id = session.get('user_id')

            # Join the necessary tables to get transactions for the user
            cursor.execute('''
                SELECT t.*
                FROM transactions t
                JOIN holdings h ON t.stock_symbol = h.stock_symbol AND t.portfolio_id = h.portfolio_id
                JOIN portfolios p ON h.portfolio_id = p.id
                WHERE p.user_id = %s
                    AND t.transaction_date BETWEEN %s AND %s
            ''', (user_id, start_date, end_date)
            )

            transactions = cursor.fetchall()

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error fetching transactions. Please try again later."

    if action == 'pdf':
        # Create a PDF document
        pdf_buffer = BytesIO()
        pdf = canvas.Canvas(pdf_buffer)

        # Customize your PDF content here, for example:
        pdf.drawString(50, 800, "Transactions:"+start_date+" to "+end_date)
        pdf.setFont("Helvetica", 10)

        y_position = 780
        for transaction in transactions:
            pdf.drawString(50, y_position, f"Transaction ID: {transaction[0]}, , Portfolio: {transaction[1]}, Stock: {transaction[2]}, Action: {transaction[3]}, Date: {transaction[4]}, Amount: {transaction[5]}, P/L: {transaction[6]}")
            y_position -= 20

        pdf.showPage()
        pdf.save()

        # Set up the response to offer the PDF for download
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=transactions.pdf'

        return response
    
    else:
        return render_template('transactions.html', transactions=transactions)
  

@app.route('/total_profit_loss', methods=['GET'])
def total_profit_loss():
    # Get the search query from the request
    portfolio_id = request.args.get('portfolio_id')

    # Fetch the transactions from the database for the logged-in user
    try:
        with mysql.connector.connect(
                host="DESKTOP-SDJEFAT",
                user="sofia",
                password="plokijuh",
                database="ai_news"
        ) as db:
            cursor = db.cursor()

            # Assuming you have a user_id stored in the session
            user_id = session.get('user_id')

            # Join the necessary tables to get transactions for the user
            cursor.execute('''
                SELECT SUM(profit_loss)
                FROM holdings
                WHERE portfolio_id = %s
            ''', (portfolio_id,)
            )

            total_profit_loss = cursor.fetchone()[0]

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error fetching transactions. Please try again later."

    return redirect(url_for('portfolio', total_profit_loss=total_profit_loss, portfolio_id=portfolio_id))

@app.route('/search_transactions', methods=['GET'])
def search_transactions():
    # Get the search query from the request
    search_query = request.args.get('search_query')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    print(search_query, start_date, end_date)

    # Fetch the transactions from the database for the logged-in user
    try:
        with mysql.connector.connect(
                host="DESKTOP-SDJEFAT",
                user="sofia",
                password="plokijuh",
                database="ai_news"
        ) as db:
            cursor = db.cursor()

            # Assuming you have a user_id stored in the session
            user_id = session.get('user_id')

            # Join the necessary tables to get transactions for the user
            cursor.execute('''
                SELECT t.*
                FROM transactions t
                JOIN holdings h ON t.stock_symbol = h.stock_symbol AND t.portfolio_id = h.portfolio_id
                JOIN portfolios p ON h.portfolio_id = p.id
                WHERE p.user_id = %s
                    AND t.transaction_date BETWEEN %s AND %s
            ''', (user_id, start_date, end_date)
            )

            transactions = cursor.fetchall()

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error fetching transactions. Please try again later."

    return render_template('transactions.html', transactions=transactions) 


@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/process_login', methods=['POST'])
def process_login():
    # Access form data
    username = request.form.get('username')
    password = request.form.get('password')
    
    try:
        with mysql.connector.connect(
            host="DESKTOP-SDJEFAT",
            user="sofia",
            password="plokijuh",
            database="ai_news"
        ) as db:
            cursor = db.cursor()
            cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
            user = cursor.fetchone()
            
            if user:
                session['user_id'] = user[0]
                return redirect(url_for('dashboard', user_id=user[0]))
            else:
                return render_template('login.html', error='Invalid credentials')
    
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error logging in. Please try again later."

@app.route('/logout')
def logout():
    # Clear the user's session
    session.pop('user_id', None)

    # Redirect to the login page or home page
    return redirect(url_for('login'))

@app.route('/process_form', methods=['POST'])
def process_form():
    # Access form data
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    
    if password!=confirm_password: return "Passwords must match."
    
    try:
        with mysql.connector.connect(
            host="DESKTOP-SDJEFAT",
            user="sofia",
            password="plokijuh",
            database="ai_news"
        ) as db:
            cursor = db.cursor()
            cursor.execute('INSERT INTO users (first_name, last_name, username, email, password) VALUES (%s, %s, %s, %s, %s)',
                           (first_name, last_name, username, email, password))
            
            db.commit()
            
        # Fetch the ID of the newly created user
            cursor.execute('SELECT LAST_INSERT_ID()')
            user_id = cursor.fetchone()[0]

        # Redirect to the dashboard page for the newly created user
        return redirect(url_for('dashboard', user_id=user_id))
    
    except IntegrityError as ie:
        if "username" in str(ie):
            return "Username already exists. Please choose a different one."
        elif "email" in str(ie):
            return "Email already exists. Please log in."
        else:
            print(f"IntegrityError: {ie}")
            return "Error creating the account. Please try again later."
    
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error creating the account. Please try again later."
    


if __name__ == '__main__':
    app.run(debug=True)