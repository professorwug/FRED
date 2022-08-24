# Adapted with gracious thanks from https://andrewm4894.com/2019/04/27/parallel-jupyter-notebooks/
import papermill as pm
import multiprocessing
import os
import argparse
import json


def run_papermill(config):
	''' Function to run notebook(s) in parallel using papermill.
	'''
	
	# get some variables from the config being run
	config = config['config'] #a bit ugly
	notebook = config['notebook']
	output_label = config["output_label"]
	
	# get name of notebook
	notebook_name = notebook.split('/')[-1].replace('.ipynb','')
	output_dir = f'papermilled/{notebook_name}/{output_label}'

	# print config to be run
	print("-"*50)
	print(output_label)
	print("-"*50)
	
	# make output dir if need to
	if not os.path.exists(output_dir):
		os.makedirs(output_dir)
	output_path = f'{output_dir}/{notebook_name}_{output_label}.ipynb'
	output_path_backup = output_path.replace('.ipynb','_backup.ipynb')

	# rename existing output file if need to
	if os.path.exists(output_path):
		# remove existing backup file if there is one
		if os.path.exists(output_path):
			os.remove(output_path_backup)
		# rename existing output file
		os.rename(output_path,output_path_backup)

	# run notebook using papermill
	global kernel
	pm.execute_notebook(
		notebook,
		output_path,
		parameters=dict(config=config),
		kernel_name = kernel
		)


# add args
parser = argparse.ArgumentParser(description='Batch run some notebooks.')
parser.add_argument(
	'--config_file',
	type=str, 
	default='configs.json', 
	help='point to the config file you want to use.'
	)
parser.add_argument(
	'--run_mode',
	type=str, 
	default='parallel', 
	help="If set to 'parallel', then run using multiprocessing, just sequential for any other value."
	)
parser.add_argument(
	'--kernel',
	type=str,
	help="Name of python kernel to run notebooks in"
)

# parse args
args = parser.parse_args()
config_file = args.config_file
run_mode = args.run_mode
kernel = args.kernel

# read in config_file
with open(config_file) as json_file:  
	configs = json.load(json_file)

		
if __name__ == '__main__':
	
	# loop over each config
	for config in configs:
		
		# pass the config keys in a dict with known name for unpacking by the run_papermill function
		config_dict = [{'config':configs[config]}]
		# print(config_dict)
		if run_mode == 'parallel':
			p = multiprocessing.Process(
				target=run_papermill,
				args=(config_dict) 
			)
			p.start()
		else:
			run_papermill(config_dict)
