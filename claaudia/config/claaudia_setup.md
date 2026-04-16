# How to run the system in Claaudia

## Step 1. Accept the terms of the MedGemma model you are going to use

[MedGemma-27b-text-it](https://huggingface.co/google/medgemma-27b-text-it)

[MedGemma-4b-it](https://huggingface.co/google/medgemma-4b-it)

---
## Step 2. Create a token in hugging face to use the open-weight models

Create a token [here](https://huggingface.co/settings/tokens) following next steps:
- Create new token -> Token type: Read -> Write a token name -> Create it and copy the token value

---
## Step 3. Paste the token value in Claaudia

In your home directory, create a directory `~/.cache/huggingface` and a file called `token` with your token value.

---
## Step 4. Create a ssh key to clone and work with the repository

Inside of claaudia, create a ssh key in your home directory.
```bash
ssh-keygen
```

Then copy your public key (file `~/.ssh/id_rsa.pub`) and create a ssh key following in github: Settings -> SSH and GPG keys -> New SSH key. There you will have to introduce a `Title` to recognize this key (for example, SSH claaudia), keep key type as `Authentication key` and paste your public key (file `~/.ssh/id_rsa.pub`, COMPLETE MESSAGE) in `Key` section.

You will also need to initialize your username and email to work with github:
```bash
git config --global user.name "YourUsername"
git config --global user.email youremail@example.com
```

---
## Step 5. Fix your ssh common port to work properly with github

As you are already connected into claaudia using ssh (port 22), you will have to change it by changing your default ssh port to use github:
```bash
nano ~/.ssh/config
```

And paste inside next text:
```bash
Host github.com
   Hostname ssh.github.com
   Port 443
   User git
   IdentityFile ~/.ssh/id_rsa
```

In case you have any issue with permissions, just need to fix next file:
```bash
chmod 600 ~/.ssh/config
```

---
## Step 6. Navigate into the project group directory and create your own working repository

```bash
cd /ceph/project/C2_AAHS
mkdir your_name
git clone git@github.com:pebb9/agentic-ai-healthcare-system.git
cd agentic-ai-healthcare-system
```

---
## Step 7. Create or change into your current working branch in the repository

New branches should come from current develop state and have next format: `feature/new_action_to_develop`.
```bash
git checkout -b feature/new_action_to_develop
```
---
## Step 8. Run the current system using Medgemma-27-it model
<b>IMPORTANT:</b> Move into directory `claaudia`. Then, run the automated file `start_27b-text-it.sh`.

```bash
cd claaudia
sh start_27b-text-it.sh
```

There are 2 more ways to run the project:
1. Using medgemma-4b-it model. Change tools.py file:
    ```python
    # Line 20
    from llm.llm_4b_it import ask_medgemma
    ```

    Also, the automated file to run the project changes because does not need as much memory as 27b model.
    ```bash
    cd claaudia
    sh start_27b-text-it.sh
    ```

2. (Local running) Using an API. Change tools.py file:
    ```python
    # Line 20
    from llm.llm_API import ask_medgemma
    ```

There is also a way to evaluate the system using sbatch instead of srun, meaning that you can leave the system runnnig until there are free resources and check it after running (check `start-evaluation.sh` file to find out where is the output of the evaluation).

```python
cd claaudia
sbatch start_evaluation.sh
```

---
