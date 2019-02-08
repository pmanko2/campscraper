import time
import os
from selenium.common.exceptions import NoSuchElementException
from twilio.rest import Client
import argparse
from selenium import webdriver
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

TWILIO_ACCOUNT = os.environ.get('TWILIO_ACCOUNT')
TWILIO_ID = os.environ.get('TWILIO_ID')
TWILIO_FROM = os.environ.get('TWILIO_FROM')
TWILIO_TO = os.environ.get('TWILIO_TO')

DATE_FORMAT = "%m/%d/%Y"


def valid_date(date_string):
    try:
        return datetime.strptime(date_string, DATE_FORMAT)
    except ValueError:
        msg = "No a valid date: {}".format(date_string)
        raise argparse.ArgumentTypeError(msg)


def send_availability_message(available, dates_available, campsite_url):
    if not available:
        return

    twilio_client = Client(TWILIO_ACCOUNT, TWILIO_ID)

    specific_campsites = "(sites {})".format(' '.join(available)) if len(available) <= 5 else ""
    campsite_message = "\n\nI found {} campsites available for the dates {} {}. " \
                       "Go to {} to reserve!".format(len(available), dates_available, specific_campsites, campsite_url)

    twilio_client.messages.create(to=TWILIO_TO, from_=TWILIO_FROM, body=campsite_message)


def get_load_more_button():
    try:
        load_more_button = driver.find_element_by_class_name('load-more-btn')
    except NoSuchElementException:
        load_more_button = None

    return load_more_button


def load_all_campsites():
    # load all available campsites by continuously pressing the "Load More" button
    main_availability = driver.find_element_by_id('per-availability-main')
    driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', main_availability)
    load_more_button = get_load_more_button()

    while load_more_button is not None:
        driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', main_availability)
        try:
            load_more_button.click()
        except Exception as e:
            print('Unable to click load more button: {}'.format(e))
            return

        load_more_button = get_load_more_button()


def determine_current_date(month_year_string, day_string, list_of_days):
    if '/' in month_year_string:
        first_day_index = list_of_days.index('1')
        month_ending_days = list_of_days[:first_day_index]
        month_split = month_year_string.split(' / ')

        month_ending = month_split[0]
        month_starting = month_split[1].split()[0]

        year = month_split[1].split()[1]
        current_date_month = month_ending if day_string in month_ending_days else month_starting
    else:
        current_date_month = month_year_string.split()[0]
        year = month_year_string.split()[1]

    return datetime.strptime("{} {} {}".format(day_string, current_date_month, year), "%d %b %Y")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('campsite_url', help='recreation.gov url to reservation site of campsite')
    parser.add_argument('start_date', help='Camping start date - format MM/DD/YYYY', type=valid_date)
    parser.add_argument('end_date', help='Camping end date - format MM/DD/YYYY', type=valid_date)
    args = parser.parse_args()

    start_date = args.start_date.strftime(DATE_FORMAT)
    end_date = args.end_date.strftime(DATE_FORMAT)
    delta = args.end_date - args.start_date
    dates_to_verify = []

    for i in range(delta.days + 1):
        date_to_verify = args.start_date + timedelta(i)
        dates_to_verify.append(date_to_verify.strftime(DATE_FORMAT))

    if not dates_to_verify:
        raise IOError('Unable to find any dates to verify reservations for. '
                      'Start date is {} and end date is {}'.format(start_date, end_date))

    # create a new Firefox session
    driver = webdriver.Firefox()
    driver.implicitly_wait(30)
    driver.get(args.campsite_url)

    # input the desired date into the date picker
    date_input = driver.find_element_by_name("single-date-picker")
    date_input.clear()
    date_input.send_keys(start_date)

    # refresh data with new date and wait some time for refresh to finish
    refresh_data_button = driver.find_element_by_class_name('rec-button-link-small')
    refresh_data_button.click()
    time.sleep(3)

    # make sure all campsites are loaded
    load_all_campsites()

    # need header columns as they contain date information for the table
    page_source = BeautifulSoup(driver.page_source, 'lxml')
    availability_table = page_source.find("table", id='availability-table')
    header_cols = [date_span.string for date_span in availability_table.thead.tr.findAll('span', {'class': 'date'})]

    # get all elements of the column we are interested in
    availability_rows = availability_table.tbody.findAll('tr')
    month_year_header = page_source.find('div', {'class': 'rec-month-availability-date-title'}).string

    campsites_available = []
    for row in availability_rows:
        campsite = row.find('button', {'class': 'rec-availability-item'}).string
        dates = row.findAll('button', {'class': 'rec-availability-date'})
        dates_to_verify_for_site = dates_to_verify.copy()

        for index, date in enumerate(dates):
            current_date = determine_current_date(month_year_header, header_cols[index], header_cols)
            current_date_string = current_date.strftime(DATE_FORMAT)

            if date.string == 'A' and current_date_string in dates_to_verify_for_site:
                dates_to_verify_for_site.remove(current_date_string)

            if len(dates_to_verify_for_site) == 0:
                campsites_available.append(campsite)
                break

    dates_available_string = start_date if start_date == end_date else "{} to {}".format(start_date, end_date)
    send_availability_message(campsites_available, dates_available_string, args.campsite_url)

    driver.close()


