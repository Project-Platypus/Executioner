'''
Created on Jul 30, 2015

@author: dhadka
'''
import os
import logging
import subprocess
import shlex
import utils
import tempfile
import socket
import time
from exceptions import TaskError
from threading import Thread
from StringIO import StringIO

class Task(object):
    '''
    Generic tasks, subclasses must override run(env).
    '''
    
    def __init__(self):
        super(Task, self).__init__()
        
    def run(self, env):
        """
        Runs the task.
        
        A task is an action performed by Executioner.  All tasks must implement
        the run method.
        
        Args:
            env: A dict storing the current Executioner environment.  Tasks may
                get and set values in the environment as needed.
        """
        raise NotImplementedError("Tasks must define the run method")
    
    
class CreateTempDir(Task):
    '''
    Creates a new, empty temporary directory and sets WORK_DIR to this
    temporary directory.
    '''
    
    def __init__(self):
        super(CreateTempDir, self).__init__()
        
    def run(self, env):
        logging.info("Creating temporary directory")
        dir = tempfile.mkdtemp()
        env["WORK_DIR"] = dir
        logging.info("Successfully created temporary directory: " + dir)
        
        
class DeleteTempDir(Task):
    '''
    Deletes the temporary directory created by CreateTempDir.
    '''
    
    def __init__(self):
        super(DeleteTempDir, self).__init__()
        
    def run(self, env):
        if not "WORK_DIR" in env:
            logging.error("WORK_DIR not defined")
            raise TaskError("WORK_DIR not defined")
        
        dir = env["WORK_DIR"]
        logging.info("Deleting temporary directory: " + dir)
        utils.remove(dir)
        logging.info("Successfully deleted temporary directory")
        
        
class SetWorkDir(Task):
    '''
    Sets the WORK_DIR.
    '''
    
    def __init__(self, dir):
        super(SetWorkDir, self).__init__()
        self.dir = dir
        
    def run(self, env):
        logging.info("Setting work directory")
        env["WORK_DIR"] = self.dir
        logging.info("Successfully set work directory: " + self.dir)   
        
        
class Delete(Task):
    '''
    Deletes a file or directory.
    '''
    
    def __init__(self, path):
        super(Delete, self).__init__()
        self.path = path
        
    def run(self, env):
        logging.info("Deleting " + str(self.path))
        
        if isinstance(self.path, list) or isinstance(self.path, tuple):
            for p in self.path:
                utils.remove(p)
        else:
            utils.remove(self.path)
        
        
class Copy(Task):
    '''
    Copies the contents of the given folder to WORK_DIR.
    '''
    
    def __init__(self, fromDir, toDir=None):
        super(Copy, self).__init__()
        self.fromDir = fromDir
        self.toDir = toDir
        
    def run(self, env):
        toDir = self.toDir
        
        if toDir is None:
            if not "WORK_DIR" in env:
                logging.error("WORK_DIR not defined")
                raise TaskError("WORK_DIR not defined")
            toDir = env["WORK_DIR"]
        
        logging.info("Copying " + self.fromDir + " to " + toDir)
        utils.copytree(self.fromDir, toDir)
        logging.info("Successfully copied folder contents")
        

class Substitute(Task):
    '''
    Substitutes ${keyword} fields in all files with their assigned values.
    '''
    
    def __init__(self, folder=None, include="*", exclude=None):
        super(Substitute, self).__init__()
        self.folder = folder
        self.include = include
        self.exclude = exclude
        
    def run(self, env):
        folder = self.folder
        
        if folder is None:
            if not "WORK_DIR" in env:
                logging.error("WORK_DIR not defined")
                raise TaskError("WORK_DIR not defined")
            folder = env["WORK_DIR"]
            
        logging.info("Substituting keywords in " + folder)
        utils.substitutetree(folder, env, self.include, self.exclude)
        logging.info("Successfully substituted keywords")
        
        
class Execute(Task):
    '''
    Executes a program.
    '''
    
    def __init__(self, command, timeout=None, ignore_stdout=False, ignore_stderr=False):
        super(Execute, self).__init__()
        self.command = command
        self.timeout = timeout
        self.ignore_stdout = ignore_stdout
        self.ignore_stderr = ignore_stderr
        
    def run(self, env):
        command = utils.substitute(self.command, env)
        
        logging.info("Executing command " + command)
        process = subprocess.Popen(shlex.split(command),
                                   stdin=subprocess.PIPE,
                                   stdout=None if self.ignore_stdout else subprocess.PIPE,
                                   stderr=None if self.ignore_stderr else subprocess.PIPE)
        
        env["PROCESS"] = process
        env["STDIN"] = process.stdin
        
        if not self.ignore_stdout:
            env["STDOUT"] = process.stdout
            
        if not self.ignore_stderr:
            env["STDERR"] = process.stderr
        
        Thread(target=utils.process_monitor, args=(process,), kwargs={ "timeout":self.timeout }).start()

        logging.info("Successfully executed command")
        

class CheckExitCode(Task):
    '''
    Checks the exit code after running Execute.
    '''
    
    def __init__(self, ok=0):
        super(CheckExitCode, self).__init__()
        
        if not isinstance(ok, list):
            self.ok = [ ok ]
        else:
            self.ok = ok
        
    def run(self, env):
        if "PROCESS" not in env:
            logging.error("PROCESS not set, call Execute before CheckExitCode")
            raise TaskError("PROCESS not set, call Execute before CheckExitCode")
        
        env["EXIT_CODE"] = env["PROCESS"].wait()
        
        if env["EXIT_CODE"] not in self.ok:
            logging.error("Execute failed, expected exit code " + str(self.ok) + ", received " + str(env["EXIT_CODE"]))
            raise TaskError("Execute failed, expected exit code " + str(self.ok) + ", received " + str(env["EXIT_CODE"]))
        
        logging.info("Exit code ok")
        
        
class WriteInput(Task):
    '''
    Writes to the STDIN of the running process.
    '''
    
    def __init__(self, input):
        super(WriteInput, self).__init__()
        self.input = input
        
    def run(self, env):
        if "STDIN" not in env:
            logging.error("STDIN not defined, run Execute first")
            raise TaskError("STDIN not defined, run Execute first")
        
        formatted_input = utils.substitute(self.input, env)
        
        logging.info("Sending input to stdin: " + formatted_input)
        stdin = env["STDIN"]
        stdin.write(formatted_input)
        stdin.flush()
        
    
        
class PrintEnv(Task):
    '''
    Prints the environment variables.
    '''
    
    def __init__(self):
        super(PrintEnv, self).__init__()
        
    def run(self, env):
        print(env)
        
        
class WriteFile(Task):
    '''
    Writes the contents of a file.
    '''
    
    def __init__(self, file, content):
        super(WriteFile, self).__init__()
        self.file = file
        self.content = content
        
    def run(self, env):
        folder = env["WORK_DIR"]
        absfile = os.path.join(folder, self.file)
        
        logging.info("Creating file " + str(absfile))
        
        with open(absfile, 'w') as file:
            file.write(utils.substitute(self.content, env))
        
        logging.info("Successfully created file")
        
        
class WriteJSON(Task):
    '''
    Writes the Python dict object to a JSON file, substituting any
    keywords.
    '''
    
    def __init__(self, json, filename, conversions={}):
        super(WriteJSON, self).__init__()
        self.json = json
        self.filename = filename
        self.conversions = conversions
        
    def run(self, env):
        import json
        sub_map = {}
        
        for key,value in self.json.iteritems():
            if isinstance(value, str):
                value = utils.substitute(value, env)
                
                if key in self.conversions:
                    value = self.conversions[key](value)
                
            sub_map[key] = value
            
        with open(self.filename, "w") as f:
            json.dump(sub_map, f)
            

class ParseOutput(Task):
    '''
    Parses the output from the last Execute call.
    '''
    
    def __init__(self, callback, file=None):
        super(ParseOutput, self).__init__()
        self.callback = callback
        self.file = file
        
    def run(self, env):
        if self.file is not None:
            with open(self.file) as f:
                results = self.callback(f)
        else:
            results = self.callback(env["STDOUT"])
            
        env.update(results)


class ParseLine(Task):
    '''
    Parses a line from the last Execute call.
    '''
    
    def __init__(self, name="output", delimiters=None, type=str):
        super(ParseLine, self).__init__()
        self.name = name
        self.delimiters = delimiters
        self.type = type
        
    def run(self, env):
        stdout = env["STDOUT"]
        line = stdout.readline()
        
        logging.info("Parsing line " + line)
        values = map(self.type, line.split(self.delimiters))
        
        if isinstance(self.name, list):
            if len(self.name) != len(values):
                logging.error("Number of parsed values (" + str(len(values)) + ") does not match number of names (" + str(len(self.name)) + ")")
                raise TaskError("Number of parsed values (" + str(len(values)) + ") does not match number of names (" + str(len(self.name)) + ")")
            
            for i, name in enumerate(self.name):
                env.update({ name : values[i] })
        else: 
            env.update({ self.name : values })
        
        
        
class Format(Task):
    '''
    Formats a field.
    '''
    
    def __init__(self, name, format="{}", rename=None):
        super(Format, self).__init__()
        self.name = name
        self.format = format
        self.rename = rename
        
    def run(self, env):
        if self.name not in env:
            logging.error(self.name + " is not set in environment")
            raise TaskError(self.name + " is not set in environment")
        
        new_name = self.rename
        if new_name is None:
            new_name = self.name
        
        logging.info("Formatting " + self.name)
        old_val = env[self.name]
        
        if callable(self.format):
            env[new_name] = self.format(old_val)
        else:
            env[new_name] = self.format.format(old_val)
            
        logging.info("Saved " + new_name + " as " + str(env[new_name]))
        

class Return(Task):
    '''
    Picks a subset of the fields to return.
    '''
    
    def __init__(self, *fields):
        super(Return, self).__init__()
        self.fields = fields
        
    def run(self, env):
        unwanted = set(env.keys()) - set(self.fields)
        
        for key in unwanted:
            del env[key]
            

class ParseXML(Task):
    '''
    Parses an XML file and reads values.
    '''
    
    def __init__(self, file):
        super(ParseXML, self).__init__()
        self.file = file
        self.fields = []
        
    def get(self, xpath, key, conversion=str):
        self.fields.append((xpath, key, conversion))
        return self
        
    def run(self, env):
        try:
            from lxml import etree
        except ImportError:
            logging.warn("Unable to import lxml, using ElementTree instead.  Some XPath functionality may be limited")
            import ElementTree as etree
            
        logging.info("Parsing XML file " + str(self.file))
        
        tree = etree.parse(self.file)
        
        for (xpath,key,conversion) in self.fields:
            values = tree.xpath(xpath)
            logging.info("Found " + str(len(values)) + " matches for " + str(xpath))
            
            if len(values) == 1:
                env[key] = conversion(values[0] if isinstance(values[0], str) else values[0].text)
            else:
                env[key] = map(conversion, [value if isinstance(value, str) else value.text for value in values])
                
            logging.info("Setting " + key + " to " + str(env[key]))
                
                
class ParseJSON(Task):
    '''
    Parses a JSON file and reads values.
    '''
    
    def __init__(self, file):
        super(ParseJSON, self).__init__()
        self.file = file
        self.fields = []
        
    def get(self, xpath, key, conversion=str):
        self.fields.append((xpath, key, conversion))
        return self
        
    def run(self, env):
        import json
        from jsonpath_rw import parse
        logging.info("Parsing JSON file " + str(self.file))
        
        with open(self.file) as f:
            content = json.load(f)
            
            for (xpath,key,conversion) in self.fields:
                expr = parse(xpath)
                values = expr.find(content)
                logging.info("Found " + str(len(values)) + " matches for " + str(xpath))
                
                if len(values) == 1:
                    if isinstance(values[0].value, list):
                        env[key] = map(conversion, values[0].value)
                    else:
                        env[key] = conversion(values[0].value)
                else:
                    env[key] = map(conversion, [value.value for value in values])
                    
                logging.info("Setting " + key + " to " + str(env[key]))
                    
                    
class ParseCSV(Task):
    '''
    Parses a CSV file and extracts values.  A simple query syntax is used:
    
        VALUE if CONDITiONS
        
    The variable row is available, which is a dict mapping the column headers
    to the value for the current row.  
    
        row["key1"] if row["key2"]=="..."
        
    Internally, this is using the Python eval() function, so simple expressions,
    such as boolean logic and type conversion functions can be used if necessary.
    For example:
    
        row["key1"] if row["key2"]=="..." and float(row["key3"])>0.0
        
    If more than one row matches, then a list of values is returned.  For example,
    an entire column can be output:
    
        row["key1"]
        
    '''
    
    def __init__(self, file, **kwargs):
        super(ParseCSV, self).__init__()
        self.file = file
        self.kwargs = kwargs
        self.fields = []
        
    def get(self, expr, key, conversion=str):
        self.fields.append((expr, key, conversion))
        return self
    
    def run(self, env):
        import csv
        
        with open(self.file) as f:
            reader = csv.DictReader(f, **self.kwargs)
            results = {}

            for row in reader:
                cleanup_row = {}
                
                for key,value in row.iteritems():
                    cleanup_row[key.strip()] = value.strip() if isinstance(value, str) else value
                
                for (expr,key,conversion) in self.fields:
                    if not expr.endswith(" else None"):
                        expr += " else None"
                        
                    result = eval(expr, { "row" : cleanup_row })
                    
                    if result is not None:
                        if key not in results:
                            results[key] = [result]
                        else:
                            results[key].append(result)
                            
            for key,values in results.iteritems():
                logging.info("Found " + str(len(values)) + " matches for " + key)
                
                if len(values) == 1:
                    env[key] = conversion(values[0] if isinstance(values[0], str) else values[0].text)
                else:
                    env[key] = map(conversion, [value if isinstance(value, str) else value.text for value in values])
                    
                logging.info("Setting " + key + " to " + str(env[key]))


class Connect(Task):
    '''
    Establishes a TCP connection.
    '''
    
    def __init__(self, address=None, server=None, port=None):
        super(Connect, self).__init__()
        
        if not address and (not server or not port):
            logging.error("Connect must define an address or (server, port) pair")
            raise TaskError("Connect must define an address or (server, port) pair")
        
        if address:
            if not ":" in address:
                logging.error("Address missing port number")
                raise TaskError("Address missing port number")
            
            self.server, self.port = address.split(":")
        else:
            self.server = server
            self.port = port
            
    def run(self, env):
        if "SOCKET" in env:
            logging.error("SOCKET already defined, close prior connection first")
            raise TaskError("SOCKET already defined, close prior connection first")
        
        server = utils.substitute(self.server, env)
        port = utils.substitute(self.port, env) if isinstance(self.port, str) else self.port
        
        logging.info("Connecting to " + str(server) + ":" + str(port))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server, int(port)))
        env["SOCKET"] = s
        env["SOCKET_FILE"] = s.makefile()
        env["STDOUT"] = StringIO()
        logging.info("Successfully connected")

class Send(Task):
    '''
    Sends a message over sockets.
    '''
    
    def __init__(self, message):
        super(Send, self).__init__()
        self.message = message
            
    def run(self, env):
        if "SOCKET" not in env:
            logging.error("SOCKET not defined, call Connect first")
            raise TaskError("SOCKET not defined, call Connect first")
        
        s = env["SOCKET"]
        formatted_msg = utils.substitute(self.message, env)
        logging.info("Sending " + formatted_msg)
        s.sendall(formatted_msg)
        logging.info("Successfully sent message")
        
class Receive(Task):
    '''
    Receives a message over sockets.
    '''
    
    def __init__(self, name="STDOUT", numlines=1):
        super(Receive, self).__init__()
        self.name = name
        self.numlines = numlines
        
    def run(self, env):
        if "SOCKET" not in env:
            logging.error("SOCKET not defined, call Connect first")
            raise TaskError("SOCKET not defined, call Connect first")
        
        logging.info("Waiting to receive message")
        stdout = env["STDOUT"]
        s = env["SOCKET_FILE"]
        
        pos = stdout.tell()
        stdout.seek(0, os.SEEK_END)
        
        for i in range(self.numlines):
            line = s.readline()
            logging.info("Received line " + line)
            stdout.write(line)
        
        stdout.seek(pos)
        logging.info("Successfully received " + str(self.numlines) + " lines")
        

class Disconnect(Task):
    '''
    Disconnects the socket.
    '''
    
    def __init__(self):
        super(Disconnect, self).__init__()
        
    def run(self, env):
        if "SOCKET" not in env:
            return
        
        logging.info("Closing connection")
        s = env["SOCKET"]
        s.shutdown(1)
        s.close()
        del env["SOCKET"]
            
class Pause(Task):
    '''
    Pauses for a given number of seconds.
    '''
    
    def __init__(self, seconds):
        super(Pause, self).__init__()
        self.seconds = seconds
        
    def run(self, env):
        for i in range(self.seconds):
            logging.info("Pausing for " + str(self.seconds-i) + " seconds")
            time.sleep(1)
            
        
class PrintStderr(Task):
    '''
    Prints the contents of STDERR.
    '''
    
    def __init__(self):
        super(PrintStderr, self).__init__()
        
    def run(self, env):
        stderr = env["STDERR"]
        
        print(stderr.read())
        
        
class Assert(Task):
    '''
    Assertions, used for unit testing or validating inputs.  The environment, env,
    will be defined and can be accessed in the expression.  This method
    uses eval() and therefore should be used carefully.
    '''
    
    def __init__(self, expr, message=None):
        super(Assert, self).__init__()
        self.expr = expr
        self.message = message
        
    def run(self, env):
        logging.info("Testing assertion " + str(self.expr))
        
        if not eval(self.expr):
            logging.info("Assertion failed!")
            raise AssertionError(self.message if self.message else "Assertion failed")