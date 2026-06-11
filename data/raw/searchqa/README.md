---
dataset_info:
  features:
  - name: context
    dtype: string
  - name: question
    dtype: string
  - name: answers
    sequence: string
  - name: key
    dtype: string
  - name: labels
    list:
    - name: end
      sequence: int64
    - name: start
      sequence: int64
  splits:
  - name: train
    num_bytes: 483999103
    num_examples: 117384
  - name: validation
    num_bytes: 69647447
    num_examples: 16980
  download_size: 325197949
  dataset_size: 553646550
---
# Dataset Card for "searchqa"

Split taken from the MRQA 2019 Shared Task, formatted and filtered for Question Answering. For the original dataset, have a look [here](https://huggingface.co/datasets/mrqa).