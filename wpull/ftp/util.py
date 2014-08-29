'''Utils'''
import re


class ReplyCodes(object):
    command_okay = 200
    syntax_error_command_unrecognized = 500
    syntax_error_in_parameters_or_arguments = 501
    command_not_implemented_superfluous_at_this_site = 202
    command_not_implemented = 502
    bad_sequence_of_commands = 503
    command_not_implemented_for_that_parameter = 504
    restart_marker_reply = 110
    system_status_or_system_help_reply = 211
    directory_status = 212
    file_status = 213
    help_message = 214
    name_system_type = 215
    service_ready_in_nnn_minutes = 120
    service_ready_for_new_user = 220
    service_closing_control_connection = 221
    service_not_available_closing_control_connection = 421
    data_connection_already_open_transfer_starting = 125
    data_connection_open_no_transfer_in_progress = 225
    cant_open_data_connection = 425
    closing_data_connection = 226
    connection_closed_transfer_aborted = 426
    entering_passive_mode = 227
    user_logged_in_proceed = 230
    not_logged_in = 530
    user_name_okay_need_password = 331
    need_account_for_login = 332
    need_account_for_storing_files = 532
    file_status_okay_about_to_open_data_connection = 150
    requested_file_action_okay_completed = 250
    pathname_created = 257
    requested_file_action_pending_further_information = 350
    requested_file_action_not_taken = 450
    requested_action_not_taken = 550
    requested_action_aborted_local_error_in_processing = 451
    requested_action_aborted_page_type_unknown = 551
    requested_action_not_taken = 452
    requested_file_action_aborted = 552
    requested_action_not_taken = 553


def parse_address(text):
    '''Parse PASV address.'''
    match = re.search(
        r'\('
        r'(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*'
        r'\)',
        text)

    if match:
        return (
            '{0}.{1}.{2}.{3}'.format(int(match.group(1)),
                                     int(match.group(2)),
                                     int(match.group(3)),
                                     int(match.group(4))
                                     ),
            int(match.group(5)) << 8 | int(match.group(6))
            )
    else:
        raise ValueError('No address found')


def reply_code_tuple(code):
    '''Return the reply code as a tuple.

    Args:
        code (int): The reply code.

    Returns:
        tuple: Each item is the digit.
    '''
    return (code // 100, code // 10 % 10, code % 10)
