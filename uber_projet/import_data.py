# import data to database

import pandas as pd
from sqlalchemy import create_engine

DB_CONFIG = {
    "user": "postgres",
    "password": "4043614002", 
    "host": "localhost",
    "port": "5432",
    "database": "UberDB"
}

# create connection string
connection_str = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
engine = create_engine(connection_str)

try :
    df = pd.read_csv('Database.csv')
    column_mapping = {
        'Date': 'date',
        'Time': 'time',
        'Booking ID': 'booking_id',
        'Booking Status': 'booking_status',
        'Customer ID': 'customer_id',
        'Vehicle Type': 'vehicle_type',
        'Cancelled Rides by Customer': 'cancelled_rides_by_customer',
        'Reason for cancelling by Customer': 'reason_for_cancelling_by_customer',
        'Cancelled Rides by Driver': 'cancelled_rides_by_driver',
        'Driver Cancellation Reason': 'driver_cancellation_reason',
        'Incomplete Rides': 'incomplete_rides',
        'Incomplete Rides Reason': 'incomplete_rides_reason',
        'Booking Value': 'booking_value',
        'Ride Distance': 'ride_distance',
        'Driver Ratings': 'driver_ratings',
        'Customer Rating': 'customer_rating',
        'Payment Method': 'payment_method'
    }
    df.rename(columns=column_mapping, inplace=True)
    df.to_sql('raw_dataset', engine, schema='bronze', if_exists='append', index=False)
except Exception as e :
    print(f'error : {e}')